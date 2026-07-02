'use strict';
/*
 * A7 — "blank remote-desktop share" reproduction test.
 *
 * Drives a real moderator client (Playwright) through a share / stop-share /
 * re-share cycle N times, and after each share checks — server-side over SSH —
 * whether the outer session actually connected to the inner persistent desktop.
 * The A7 signature is: the share issues, websockify spawns the outer session,
 * but nothing connects to /run/vnc/<user> (the "accepted:" count in the
 * persistent Xvnc log does not move) → blank panel. On a blank we snapshot
 * diagnostics immediately, since the original investigation lost the trail
 * (overwritten inetd logs).
 *
 * Defaults target collaborate.freesoft.org where the ONLY account with a
 * desktop is BrentBaccala, so we drive that identity — in a dedicated meeting,
 * isolated from any live meeting. We NEVER clean up the desktop (that would
 * terminate the real user's session); we only leave the test meeting.
 *
 *   node a7-blank-second-share.cjs [N_CYCLES]     # default 8
 *
 * CAVEAT: if <user> already has an outer session (i.e. they are logged in
 * elsewhere), a blank here may reflect same-user / same-desktop spawn
 * contention rather than the original bring-up A7. The script warns when it
 * detects a pre-existing outer session; for a clean result run it when no
 * other session for <user> is active.
 *
 * Env: RD_HOST, RD_SSH, RD_USER (moderator = UNIX user with the desktop),
 *      RD_MEETING, PW_MODULE, PW_CHROME.
 */
const { execSync } = require('child_process');
const fs = require('fs');

const HOST = process.env.RD_HOST || 'collaborate.freesoft.org';
const SSH = process.env.RD_SSH || 'ubuntu@collaborate.freesoft.org';
const USER = process.env.RD_USER || 'BrentBaccala';
const MEETING = process.env.RD_MEETING || 'A7BlankShareTest';
const N = parseInt(process.argv[2] || process.env.A7_CYCLES || '8', 10);
const LOG = `/home/${USER}/.vnc/${HOST}:1.log`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function sh(cmd) { return execSync(cmd, { encoding: 'utf8' }); }
function ssh(remoteCmd) {
  const quoted = "'" + remoteCmd.replace(/'/g, "'\\''") + "'";
  return sh(`ssh -o ConnectTimeout=10 -o BatchMode=yes ${SSH} ${quoted}`);
}
function mklogin() {
  const out = ssh(`bbb-mklogin -m -M ${MEETING} -e never '${USER}'`).trim();
  return out.replace(/^https?:\/\/[^/]+/, `https://${HOST}`);
}
function loadPlaywright() {
  const cands = [process.env.PW_MODULE, 'playwright',
    '/home/claude/bigbluebutton-html-plugin-sdk/node_modules/playwright'].filter(Boolean);
  for (const c of cands) { try { return require(c); } catch (e) { /* next */ } }
  throw new Error('playwright module not found; set PW_MODULE');
}
function findChrome() {
  if (process.env.PW_CHROME) return process.env.PW_CHROME;
  const base = `${process.env.HOME}/.cache/ms-playwright`;
  const dirs = fs.existsSync(base) ? fs.readdirSync(base).filter(d => /^chromium-\d+$/.test(d)).sort() : [];
  for (const d of dirs.reverse())
    for (const sub of ['chrome-linux64/chrome', 'chrome-linux/chrome']) {
      const p = `${base}/${d}/${sub}`; if (fs.existsSync(p)) return p;
    }
  return undefined;
}
function withTimeout(promise, ms, label) {
  return Promise.race([promise,
    new Promise((_, rej) => setTimeout(() => rej(new Error(`${label} timed out after ${ms}ms`)), ms))]);
}
const evalClick = (page, fn, label) => withTimeout(page.evaluate(fn), 8000, label);

async function dismissAudioModal(page) {
  try {
    await page.waitForFunction(
      () => [...document.querySelectorAll('button')].some(b => /Listen only/i.test(b.textContent)),
      undefined, { timeout: 15000 });
    await evalClick(page, () => {
      const b = [...document.querySelectorAll('button')].find(x => /Listen only/i.test(x.textContent));
      if (b) b.click();
    }, 'dismiss-audio');
    await page.waitForFunction(() => !document.querySelector('.ReactModal__Overlay'), undefined, { timeout: 10000 })
      .catch(() => {});
  } catch (e) { /* never showed */ }
}

// Close any lingering modal (esp. the "Session Details" welcome modal that pops
// after the audio modal). Its overlay intercepts pointer events and — critically
// — leaving it up blocks the whole share flow. [data-test="closeModal"] is the
// generic BBB modal close button; fall back to an aria "Close ..." button.
async function dismissModals(page) {
  try {
    const r = await withTimeout(page.evaluate(() => {
      const overlays = document.querySelectorAll('.ReactModal__Overlay').length;
      const btn = document.querySelector('[data-test="closeModal"]')
        || [...document.querySelectorAll('button[aria-label^="Close"]')][0];
      const label = btn ? (btn.getAttribute('aria-label') || btn.getAttribute('data-test') || 'closeModal') : null;
      if (btn) btn.click();
      return { overlays, closed: label };
    }), 8000, 'dismiss-modal');
    if (process.env.A7_DEBUG) console.log(`    [dismissModals] overlays=${r.overlays} closed=${r.closed}`);
    await sleep(400);
  } catch (e) { if (process.env.A7_DEBUG) console.log('    [dismissModals] err ' + e.message.split('\n')[0]); }
}

async function join(browser, url) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  page.on('console', (m) => { const t = m.text(); if (/RemoteDesktop|plugin|SDK|manifest|Failed|error|404|forbidden/i.test(t)) console.log('  [console]', t.slice(0, 200)); });
  page.on('pageerror', (e) => console.log('  [pageerror]', String(e).slice(0, 200)));
  await page.goto(url, { waitUntil: 'load', timeout: 45000 });
  await page.waitForFunction((mtg) => document.title.includes(mtg), MEETING, { timeout: 45000 }).catch(() => {});
  await dismissAudioModal(page);
  await dismissModals(page);   // the "Session Details" welcome modal blocks the actions menu
  await page.waitForSelector('button[data-test="actionsButton"]', { timeout: 30000 }).catch(() => {});
  return { ctx, page };
}

// open actions dropdown and click a menu item whose text matches `re`
async function actionItem(page, re, label) {
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      await dismissModals(page);
      await evalClick(page, () => document.querySelector('button[data-test="actionsButton"]').click(), 'actions-open');
      if (process.env.A7_DEBUG) {
        await sleep(500);
        const st = await page.evaluate((src) => ({
          overlays: document.querySelectorAll('.ReactModal__Overlay').length,
          menuitems: document.querySelectorAll('[role="menuitem"]').length,
          targetFound: [...document.querySelectorAll('[role="menuitem"],li,button')].some(e => new RegExp(src, 'i').test(e.textContent)),
        }), re.source);
        console.log(`    [actionItem ${label} attempt ${attempt}] overlays=${st.overlays} menuitems=${st.menuitems} targetFound=${st.targetFound}`);
      }
      // Real-click the item with Playwright: a synthetic element.click() inside
      // evaluate() does NOT trigger BBB's dropdown-item handler (the modal never
      // opens), even though the same DOM click works for the plain actionsButton.
      const item = page.getByRole('menuitem', { name: re }).first();
      await item.waitFor({ state: 'visible', timeout: 7000 });
      await item.click({ timeout: 5000 });
      return true;
    } catch (e) {
      await page.keyboard.press('Escape').catch(() => {});
      await sleep(1000);
    }
  }
  return false;
}

async function share(page) {
  if (!await actionItem(page, /Share a remote desktop/, 'share-item')) return false;
  if (process.env.A7_DEBUG) {
    await sleep(600);
    const st = await page.evaluate(() => ({
      reactModals: document.querySelectorAll('.ReactModal__Content').length,
      dialogs: document.querySelectorAll('[role="dialog"]').length,
      hasURL: [...document.querySelectorAll('.ReactModal__Content,[role="dialog"]')].some(m => /Remote Desktop URL/i.test(m.textContent || '')),
    }));
    console.log(`    [share] after item-click: reactModals=${st.reactModals} dialogs=${st.dialogs} hasURL=${st.hasURL}`);
  }
  try {
    await page.waitForFunction(() => [...document.querySelectorAll('.ReactModal__Content')]
      .some(m => /Remote Desktop URL/i.test(m.textContent)), undefined, { timeout: 7000 });
    return await withTimeout(page.evaluate((host) => {
      const rd = [...document.querySelectorAll('.ReactModal__Content')].find(m => /Remote Desktop URL/i.test(m.textContent));
      if (!rd) return false;
      const inp = rd.querySelector('input[type="text"],input:not([type])');
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(inp, 'wss://' + host + '/vnc');
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      const btn = [...rd.querySelectorAll('button')].find(b => b.textContent.trim() === 'Share');
      if (!btn || btn.disabled) return false;
      btn.click(); return true;
    }, HOST), 8000, 'share-fill');
  } catch (e) { return false; }
}
const stopShare = (page) => actionItem(page, /Stop sharing remote desktop/, 'stop-item');

function probe() {
  const out = ssh(
    `printf 'ACC=%s\\n' "$(sudo grep -c 'accepted: /run/vnc/${USER}' '${LOG}' 2>/dev/null)"; ` +
    `printf 'OUTER=%s\\n' "$(ps -u ${USER} -o cmd 2>/dev/null | grep -oE 'Xtigervnc :[0-9]+ .*inetd' | grep -oE '^Xtigervnc :[0-9]+' | sort -u | tr '\\n' ',')"; ` +
    `printf 'ESTAB=%s\\n' "$(sudo ss -xp 2>/dev/null | grep '/run/vnc/${USER}' | grep -c ESTAB)"`);
  return {
    acc: parseInt((out.match(/ACC=(\d+)/) || [])[1] || '0', 10),
    estab: parseInt((out.match(/ESTAB=(\d+)/) || [])[1] || '0', 10),
    outer: ((out.match(/OUTER=(.*)/) || [])[1] || '').split(',').filter(Boolean),
  };
}
function diagnostics(i) {
  console.log(`--- A7 DIAGNOSTICS for share #${i} ---`);
  try {
    console.log(ssh(
      `echo '== outer inetd Xvnc / teacher_desktop / ssvncviewer =='; ps -u ${USER} -o pid,etimes,cmd | grep -E 'inetd|teacher_desktop|ssvncviewer' | grep -v grep | tail -25; ` +
      `echo '== ss peers on /run/vnc/${USER} =='; sudo ss -xp | grep '/run/vnc/${USER}'; ` +
      `echo '== tail persistent :1 log =='; sudo tail -18 '${LOG}'; ` +
      `echo '== journal bbb-vnc-collaborate (last 25) =='; sudo journalctl -u bbb-vnc-collaborate -n 25 --no-pager`));
  } catch (e) { console.log('(diagnostics failed: ' + e.message + ')'); }
}

(async () => {
  console.log(`# A7 test: ${N} share cycles as ${USER} in meeting ${MEETING} on ${HOST}`);
  console.log(`# (isolated meeting; the real user's live session is untouched; no desktop cleanup)`);
  const pre = probe();
  if (pre.outer.length) {
    console.log(`# WARNING: ${USER} already has an outer session ${JSON.stringify(pre.outer)} — a blank`);
    console.log(`#          here may be same-user spawn contention, not the original A7. For a clean`);
    console.log(`#          result, run when no other session for ${USER} is active.`);
  }
  const pw = loadPlaywright();
  const browser = await pw.chromium.launch({ headless: true, executablePath: findChrome(),
    args: ['--no-sandbox', '--ignore-certificate-errors'] });
  let blanks = 0, connected = 0;
  try {
    const { page } = await join(browser, mklogin());
    console.log(`# joined as ${USER}\n`);
    for (let i = 1; i <= N; i++) {
      const before = probe();
      const shared = await share(page);           // real "Share a remote desktop" via the plugin UI
      if (!shared) { console.log(`share #${i}: FAILED to issue share via UI`); await stopShare(page).catch(() => {}); blanks++; await sleep(3000); continue; }
      // Poll up to 18 s for the outer session to spawn AND connect to the inner
      // desktop (the grid takes a few seconds to enumerate + spawn its cells).
      let newOuter = [], accD = 0, spawned = false, didConnect = false;
      for (let t = 0; t < 18; t++) {
        await sleep(1000);
        const p = probe();
        newOuter = p.outer.filter((d) => !before.outer.includes(d));
        if (newOuter.length) spawned = true;
        accD = p.acc - before.acc;
        if (spawned && (accD > 0 || p.estab > before.estab)) { didConnect = true; break; }
      }
      const verdict = didConnect ? 'CONNECTED'
        : (spawned ? 'BLANK (outer spawned, NO inner connect within 18s)' : 'NO OUTER SPAWN (share issued but no /vnc session)');
      console.log(`share #${i}: newOuter=[${newOuter.join(' ') || '-'}]  accΔ=${accD}  => ${verdict}`);
      if (didConnect) connected++; else { blanks++; diagnostics(i); }
      await stopShare(page);                       // "Stop sharing remote desktop"
      await sleep(5000);                          // let the inetd session tear down before next cycle
    }
  } finally {
    await browser.close();
    console.log(`\n# summary: ${connected} connected, ${blanks} blank/failed out of ${N}`);
    console.log(`# leaving meeting ${MEETING} to time out on its own (no desktop cleanup).`);
    process.exit(blanks > 0 ? 1 : 0);
  }
})();

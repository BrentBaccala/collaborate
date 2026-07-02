'use strict';
/*
 * D3 — "double VNC websocket on re-share" regression test.
 *
 * Bug: re-sharing a remote desktop after one was already shown in the session
 * made the plugin's generic content leave and re-enter the presentation pile,
 * which tripped the "content returned to layout, forcing VNC reconnect" path
 * (meant only for screenshare interruptions). That reconnect fired while the
 * fresh /vnc websocket was still handshaking — it aborted socket #1 (browser
 * logs "can't establish a connection to wss://.../vnc") and opened socket #2,
 * so TWO websockify handlers spawned TWO tigervncservers and one was torn down.
 * The aborted socket also briefly flashed the "connection lost" overlay.
 * Fixed in plugin 2:0.3.0-13 by resetting the layout-return tracking whenever a
 * new activeConfig builds a fresh React root (commit 39111db).
 *
 * Oracle (server-side, browser-independent): each share must open EXACTLY ONE
 * /vnc websocket in the bbb-vnc-collaborate journal. The bug's signature is two
 * connections in the same window (with the same sessionToken), one aborted.
 * Secondary client signatures are asserted too: no "forcing VNC reconnect"
 * breadcrumb and no "can't establish a connection" / "WebSocket ... failed"
 * error on a plain re-share.
 *
 * The regression-critical cycle is the SECOND share onwards (the first share of
 * a session never doubled — hasEverShownContent is not yet set). We therefore
 * run >= 2 share/stop cycles and check every share, first included.
 *
 *   node d3-double-websocket.cjs [N_CYCLES]      # default 3
 *
 * Env: RD_HOST, RD_SSH, RD_USER (moderator display name = UNIX user with the
 *      desktop), RD_MEETING, PW_MODULE, PW_CHROME. Defaults target the local
 *      jammy-300.samsung test VM in a dedicated, isolated meeting.
 */
const { execSync } = require('child_process');
const fs = require('fs');

const HOST = process.env.RD_HOST || 'jammy-300.samsung';
const SSH = process.env.RD_SSH || 'ubuntu@jammy-300.samsung';
const USER = process.env.RD_USER || 'Moderator';
const MEETING = process.env.RD_MEETING || 'D3DoubleWSTest';
const N = Math.max(2, parseInt(process.argv[2] || process.env.D3_CYCLES || '3', 10));

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

// --- server-side oracle ------------------------------------------------------
function remoteEpoch() { return parseInt(ssh('date +%s').trim() || '0', 10); }
// Count /vnc WebSocket opens logged since `epoch`. `| cat` keeps grep's exit 1
// (no match) from failing the ssh; grep still prints the count to stdout.
function vncWsOpensSince(epoch) {
  const out = ssh(
    `sudo journalctl -u bbb-vnc-collaborate --since '@${epoch}' --no-pager 2>/dev/null ` +
    `| grep -c 'WebSocket connection' | cat`);
  return parseInt(out.trim() || '0', 10);
}
function vncPathsSince(epoch) {
  return ssh(
    `sudo journalctl -u bbb-vnc-collaborate --since '@${epoch}' --no-pager 2>/dev/null ` +
    `| grep -oE "Path: '/vnc[^']*'" | cat`).trim();
}

// --- BBB client driving (shared shape with a7-blank-second-share.cjs) --------
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
async function dismissModals(page) {
  try {
    await withTimeout(page.evaluate(() => {
      const btn = document.querySelector('[data-test="closeModal"]')
        || [...document.querySelectorAll('button[aria-label^="Close"]')][0];
      if (btn) btn.click();
    }), 8000, 'dismiss-modal');
    await sleep(400);
  } catch (e) { /* none */ }
}
async function join(browser, url, consoleBuf) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  page.on('console', (m) => consoleBuf.push(m.text()));
  page.on('pageerror', (e) => consoleBuf.push('[pageerror] ' + String(e)));
  await page.goto(url, { waitUntil: 'load', timeout: 45000 });
  await page.waitForFunction((mtg) => document.title.includes(mtg), MEETING, { timeout: 45000 }).catch(() => {});
  await dismissAudioModal(page);
  await dismissModals(page);   // the "Session Details" welcome modal blocks the actions menu
  await page.waitForSelector('button[data-test="actionsButton"]', { timeout: 30000 }).catch(() => {});
  return { ctx, page };
}
async function actionItem(page, re) {
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      await dismissModals(page);
      await evalClick(page, () => document.querySelector('button[data-test="actionsButton"]').click(), 'actions-open');
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
  if (!await actionItem(page, /Share a remote desktop/)) return false;
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
const stopShare = (page) => actionItem(page, /Stop sharing remote desktop/);

// A re-render breadcrumb / WS-failure signature in the console buffer slice.
const RECONNECT_RE = /forcing VNC reconnect/i;
const WSFAIL_RE = /(can.?t establish a connection to the server at wss:.*\/vnc|WebSocket connection to '[^']*\/vnc[^']*' failed)/i;

(async () => {
  console.log(`# D3 test: ${N} share/stop cycles as ${USER} in meeting ${MEETING} on ${HOST}`);
  console.log(`# oracle: each share opens exactly ONE /vnc websocket (bug = two, one aborted)\n`);
  const pw = loadPlaywright();
  const browser = await pw.chromium.launch({ headless: true, executablePath: findChrome(),
    args: ['--no-sandbox', '--ignore-certificate-errors'] });
  const consoleBuf = [];
  let failures = 0;
  try {
    const { page } = await join(browser, mklogin(), consoleBuf);
    console.log(`# joined as ${USER}\n`);
    for (let i = 1; i <= N; i++) {
      const marker = consoleBuf.length;
      const t0 = remoteEpoch();
      const shared = await share(page);
      if (!shared) { console.log(`share #${i}: FAILED to issue share via UI`); failures++; await stopShare(page).catch(() => {}); await sleep(3000); continue; }
      await sleep(6000);                       // let the websocket(s) open + spawn
      const opens = vncWsOpensSince(t0);
      const slice = consoleBuf.slice(marker);
      const reconnected = slice.some((t) => RECONNECT_RE.test(t));
      const wsFailed = slice.some((t) => WSFAIL_RE.test(t));
      const kind = i === 1 ? 'first share' : 're-share';
      const ok = opens === 1 && !reconnected && !wsFailed;
      console.log(`share #${i} (${kind}): /vnc opens=${opens}  forcedReconnect=${reconnected}  wsFail=${wsFailed}  => ${ok ? 'OK' : 'FAIL'}`);
      if (!ok) {
        failures++;
        console.log(`    paths since share:\n${vncPathsSince(t0).split('\n').map(l => '      ' + l).join('\n')}`);
        const sig = slice.filter((t) => RECONNECT_RE.test(t) || WSFAIL_RE.test(t) || /RemoteDesktop\]/.test(t));
        if (sig.length) console.log(`    console:\n${sig.map(l => '      ' + l.slice(0, 180)).join('\n')}`);
      }
      await stopShare(page);
      await sleep(5000);                       // let the inetd session tear down before the next cycle
    }
  } finally {
    await browser.close();
    console.log(`\n# summary: ${N - failures}/${N} shares opened exactly one /vnc websocket`);
    console.log(`# leaving meeting ${MEETING} to time out on its own (no desktop cleanup).`);
    process.exit(failures > 0 ? 1 : 0);
  }
})();

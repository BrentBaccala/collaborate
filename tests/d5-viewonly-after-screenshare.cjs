'use strict';
/*
 * D5 — remote-desktop input must not be silently locked after a screenshare
 * round-trip.
 *
 * Symptom (user-reported): share a remote desktop (unlocked), then start and
 * stop a screenshare. When the remote desktop returns to the presentation area,
 * input is LOCKED even though the lock button still shows "unlocked". i.e. the
 * displayed `locked` state and the live noVNC `viewOnly` disagree.
 *
 * Mechanism under test: a screenshare swaps our generic content out of the
 * presentation pile and (unlike a re-share) leaves `activeConfig` unchanged, so
 * on return the "content returned to layout, forcing VNC reconnect" effect
 * fires and remounts VncDisplay with a fresh RFB. The oracle checks that the
 * fresh connection's `viewOnly` matches the (unlocked) button.
 *
 * Oracle (client-side): read the live noVNC RFB via React fiber traversal from
 * its <canvas> and compare `rfb._viewOnly` to the lock button's aria-label
 * ("Lock remote desktop controls" = currently unlocked). A fail is
 * button-unlocked + rfb._viewOnly===true (or the RFB never reconnecting).
 *
 * Screenshare is driven for real via getDisplayMedia; chromium is launched with
 * fake-media flags so the picker is auto-accepted headlessly. If the browser
 * can't start a screen capture in this environment the run reports SKIP (the
 * swap-out never happened) rather than a false pass.
 *
 *   node d5-viewonly-after-screenshare.cjs [N_CYCLES]     # default 2
 *
 * Env: RD_HOST, RD_SSH, RD_USER, RD_MEETING, PW_MODULE, PW_CHROME.
 */
const { execSync } = require('child_process');
const fs = require('fs');

const HOST = process.env.RD_HOST || 'jammy-300.samsung';
const SSH = process.env.RD_SSH || 'ubuntu@jammy-300.samsung';
const USER = process.env.RD_USER || 'Moderator';
// Unique per run (pid) so a leftover share from a prior run can't confuse the
// Actions menu ("Stop sharing" vs "Share a remote desktop").
const MEETING = process.env.RD_MEETING || `D5ViewOnly-${process.pid}`;
const N = Math.max(1, parseInt(process.argv[2] || process.env.D5_CYCLES || '2', 10));

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
  await dismissModals(page);
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

// --- the oracle: live RFB viewOnly (via fiber) vs the lock button ------------
async function probeVnc(page) {
  return await page.evaluate(() => {
    function fiberOf(el) {
      if (!el) return null;
      const k = Object.keys(el).find((k) => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
      return k ? el[k] : null;
    }
    function findRfb() {
      for (const c of document.querySelectorAll('canvas')) {
        let f = fiberOf(c) || fiberOf(c.parentElement) || fiberOf(c.parentElement && c.parentElement.parentElement);
        let g = 0;
        while (f && g++ < 300) { if (f.stateNode && f.stateNode.rfb) return f.stateNode.rfb; f = f.return; }
      }
      return null;
    }
    const rfb = findRfb();
    const lockBtn = [...document.querySelectorAll('button[aria-label]')]
      .find((b) => /remote desktop controls/i.test(b.getAttribute('aria-label')));
    const lbl = lockBtn ? lockBtn.getAttribute('aria-label') : null;
    // "Lock remote desktop controls" => currently UNLOCKED; "Unlock ..." => LOCKED
    const buttonSaysLocked = lbl ? /^Unlock/i.test(lbl) : null;
    return {
      rfbFound: !!rfb,
      viewOnly: rfb ? !!rfb._viewOnly : null,
      state: rfb ? rfb._rfbConnectionState : null,
      lockLabel: lbl,
      buttonSaysLocked,
    };
  });
}
// wait until the RFB is present and connected (after a reconnect it briefly vanishes)
async function waitConnected(page, ms) {
  const t0 = Date.now();
  let last = null;
  while (Date.now() - t0 < ms) {
    last = await probeVnc(page);
    if (last.rfbFound && last.state === 'connected') return last;
    await sleep(500);
  }
  return last;
}

async function startScreenshare(page) {
  try {
    const btn = page.getByRole('button', { name: /Share your screen/i }).first();
    await btn.waitFor({ state: 'visible', timeout: 8000 });
    await btn.click({ timeout: 5000 });
    return true;
  } catch (e) { return false; }
}
async function stopScreenshare(page) {
  try {
    const btn = page.getByRole('button', { name: /Stop (screen ?sharing|sharing your screen)|Unshare screen/i }).first();
    await btn.waitFor({ state: 'visible', timeout: 8000 });
    await btn.click({ timeout: 5000 });
    return true;
  } catch (e) { return false; }
}

const LEFT_PILE = /showingContent: true → false/;

(async () => {
  console.log(`# D5 test: remote-desktop input state after screenshare round-trip`);
  console.log(`# as ${USER} in meeting ${MEETING} on ${HOST}; ${N} cycle(s)\n`);
  const pw = loadPlaywright();
  // Screen capture (getDisplayMedia) needs a real display; run headed under a
  // virtual X server (xvfb-run) so the screenshare actually starts. Headless
  // chromium has no capture source, so the swap-out never happens and the run
  // SKIPs rather than false-passing. Set D5_HEADED=1 (with $DISPLAY, e.g. via
  // `xvfb-run -a`) to exercise the screenshare path.
  const headed = !!process.env.D5_HEADED && !!process.env.DISPLAY;
  const browser = await pw.chromium.launch({
    headless: !headed, executablePath: findChrome(),
    args: ['--no-sandbox', '--ignore-certificate-errors',
      '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
      '--auto-select-desktop-capture-source=Entire screen'],
  });
  const consoleBuf = [];
  let failures = 0, skipped = 0;
  try {
    const { page } = await join(browser, mklogin(), consoleBuf);
    console.log(`# joined as ${USER}`);
    // Ensure a remote desktop is up: reuse an existing share (leftover from a
    // prior run) if present, else share one.
    let base = await waitConnected(page, 6000);
    if (!base || !base.rfbFound) {
      if (!await share(page)) { console.log('FATAL: could not share the remote desktop'); process.exit(2); }
      base = await waitConnected(page, 20000);
    }
    console.log(`baseline: ${JSON.stringify(base)}`);
    if (!base || !base.rfbFound || base.state !== 'connected' || base.viewOnly !== false) {
      console.log('FATAL: remote desktop did not come up interactive at baseline'); process.exit(2);
    }
    for (let i = 1; i <= N; i++) {
      const mark = consoleBuf.length;
      if (!await startScreenshare(page)) { console.log(`cycle #${i}: SKIP — no "Share your screen" button`); skipped++; continue; }
      await sleep(2500);
      const ss = await page.evaluate(() => ({
        stopBtn: [...document.querySelectorAll('button[aria-label]')].some((b) => /stop (screen ?sharing|sharing your screen)|unshare screen/i.test(b.getAttribute('aria-label'))),
        gdm: !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia),
      }));
      console.log(`cycle #${i}: after share-screen click: screenshareActive=${ss.stopBtn} getDisplayMedia=${ss.gdm}`);
      // wait up to 8 s for our content to actually leave the pile
      let leftPile = false;
      for (let t = 0; t < 16; t++) { await sleep(500); if (consoleBuf.slice(mark).some((l) => LEFT_PILE.test(l))) { leftPile = true; break; } }
      if (!leftPile) {
        // Observed on jammy-300 as a solo presenter: the screenshare starts
        // (screenshareActive/getDisplayMedia true above) yet the remote-desktop
        // generic content stays CURRENT in the presentation pile, so the
        // "content returned to layout" reconnect never fires and the desync
        // can't arise. The swap-out likely needs a viewer / the collaborate
        // teacher-grid deployment. Report SKIP rather than a false pass.
        console.log(`cycle #${i}: SKIP — screenshare started but did not swap the remote desktop out of the pile ` +
          `(reconnect path not exercised on this deployment)`);
        await stopScreenshare(page).catch(() => {});
        skipped++; await sleep(3000); continue;
      }
      await sleep(1500);
      await stopScreenshare(page);
      // content returns → forced reconnect → wait for the fresh RFB to connect
      const after = await waitConnected(page, 25000);
      const desync = after && after.buttonSaysLocked === false && after.viewOnly === true;
      const ok = after && after.rfbFound && after.state === 'connected' && after.viewOnly === false && after.buttonSaysLocked === false;
      console.log(`cycle #${i}: after return ${JSON.stringify(after)} => ${ok ? 'OK' : (desync ? 'FAIL (button unlocked but input viewOnly)' : 'FAIL')}`);
      if (!ok) failures++;
      await sleep(2000);
    }
  } finally {
    await browser.close();
    console.log(`\n# summary: ${failures} desync/fail, ${skipped} skipped of ${N} cycle(s)`);
    console.log(`# leaving meeting ${MEETING} to time out on its own.`);
    if (failures > 0) process.exit(1);
    if (skipped === N) process.exit(3);   // path never exercised — inconclusive
    process.exit(0);
  }
})();

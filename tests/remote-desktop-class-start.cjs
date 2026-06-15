#!/usr/bin/env node
/*
 * remote-desktop-class-start.cjs
 *
 * End-to-end test of the collaborate VNC desktop spawn path
 * (vnc_collaborate/websockify.py: new_websocket_client -> ensure_vnc_server
 * -> start_VNC_server) under the real class-start condition that exposed two
 * defects, both now fixed by ensure_vnc_server:
 *
 *   (A) Display-number collision. When many desktops spawn at once,
 *       tigervncserver's "pick the lowest free X display" check races: two
 *       spawns grab the same :N and the loser dies fatally ("Server is already
 *       active for display N").
 *   (B) Spawn-lock deadlock. start_VNC_server waited for the new desktop's
 *       UNIX socket to appear with NO timeout, while ensure_vnc_server held
 *       that user's per-user spawn lock -- so a spawn that died (e.g. from A)
 *       hung forever holding the lock, permanently black-screening that
 *       student and stacking every later reconnect behind the held lock.
 *
 *   Original write-up: ~/project/reports/bbb-collaborate-desktop-bugs.md.
 *
 * Unlike a reproduction, this exercises the *deployed* service: real BBB
 * clients open real authenticated /vnc websockets through nginx, so the code
 * actually under test is whatever is installed on the host.
 *
 * Mechanism (see bbb-plugin-remote-desktop component.tsx):
 *   - One moderator + N students join the same meeting, each in its own browser
 *     context (so each has its own authenticated session: /vnc auth needs the
 *     user's JSESSIONID + sessionToken from a real login, and the user must be a
 *     live getMeetings attendee).
 *   - The moderator shares a remote desktop ONCE, pointed at wss://HOST/vnc
 *     (the collaborate websockify path -- NOT the default /proxy/). That pushes
 *     one entry on the 'remoteDesktop' data channel; every client reacts by
 *     opening wss://HOST/vnc?sessionToken=<its own> at the same time.
 *   - So one share fans out to N near-simultaneous ensure_vnc_server spawns --
 *     the concurrent contention that exposes the defects.
 *
 * Oracle (checked over SSH on the host):
 *   PASS iff every student's persistent desktop socket /run/vnc/<Student> comes
 *   up within the timeout AND no student's spawn lock is left wedged -- a held
 *   /run/vnc/.<Student>.spawnlock is the signature of the deadlock (B).
 *
 * With the unpatched websockify, a lost display race (A) hangs start_VNC_server
 * while holding the lock (B) -> that student never appears and its spawnlock
 * stays wedged -> FAIL. With ensure_vnc_server (bounded wait + retry-with-jitter,
 * lock always released) every student should come up -> PASS.
 *
 * Usage:
 *   node remote-desktop-class-start.cjs [N_STUDENTS]
 * Env overrides:
 *   RD_HOST      BBB hostname for the browser/URLs   (default jammy-300.samsung)
 *   RD_SSH       ssh target with sudo on the host     (default ubuntu@jammy-300.samsung)
 *   RD_MEETING   meeting name                         (default RDClassStart)
 *   RD_STUDENTS  number of students                   (default 4)
 *   RD_MODERATOR dummy moderator name                 (default RDTeacher)
 *   RD_PREFIX    dummy student name prefix            (default Student)
 *                -- override RD_MODERATOR/RD_PREFIX on a shared/production host
 *                   so the dummy accounts (and the scoped cleanup) can't collide
 *                   with real ones.
 *   RD_SPAWN_SECS first-phase wait for the sockets before declaring a wedge
 *                (default 60). Lower it (with RD_DIAGNOSE) to deterministically
 *                catch a slow spawn at the cutoff and watch whether it heals.
 *   RD_DIAGNOSE  if set, on a wedge don't kill immediately: keep polling for the
 *                stuck sockets (to tell a SLOW spawn from a TRUE deadlock) and
 *                dump each stuck user's session journal / lock holder / log.
 *   RD_DIAGNOSE_SECS  how long to watch in diagnose mode (default 240)
 *   RD_KEEP      if set, leave the desktops up after the run (don't clean)
 *   PW_MODULE    path to a playwright module
 *   PW_CHROME    path to a chromium executable
 *
 * Requires: a running BBB host with the collaborate stack and bbb-auth-jwt
 * (bbb-mklogin), reachable by SSH (for login URLs + the server-side oracle).
 */
'use strict';
const { execSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');

const HOST = process.env.RD_HOST || 'jammy-300.samsung';
const SSH = process.env.RD_SSH || 'ubuntu@jammy-300.samsung';
const SECRET = process.env.RD_SECRET || 'bbbci';   // BBB shared secret, for the end-meeting teardown
const MEETING = process.env.RD_MEETING || 'RDClassStart';
const N = parseInt(process.argv[2] || process.env.RD_STUDENTS || '4', 10);
// Dummy account names -- override on a shared/production host so they can't
// collide with (or have cleanup touch) real accounts. fullName == UNIX user
// (spaces are squashed), and ALL kill/rm/deluser is scoped to exactly these.
const MODERATOR = process.env.RD_MODERATOR || 'RDTeacher';
const STUDENT_PREFIX = process.env.RD_PREFIX || 'Student';
// First-phase poll: how long to wait for the sockets before declaring a wedge.
// Lower it (with RD_DIAGNOSE) to deterministically catch a slow spawn at the
// cutoff and then watch whether it heals.
const SPAWN_TIMEOUT_MS = parseInt(process.env.RD_SPAWN_SECS || '60', 10) * 1000;

const students = Array.from({ length: N }, (_, i) => `${STUDENT_PREFIX}${String(i + 1).padStart(2, '0')}`);
const allUsers = [MODERATOR, ...students];

// ---- locate playwright + a chromium binary (browsers here predate the sdk's
//      pinned revision, so launch with an explicit executablePath) -----------
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
  for (const d of dirs.reverse()) {
    for (const sub of ['chrome-linux64/chrome', 'chrome-linux/chrome']) {
      const p = `${base}/${d}/${sub}`;
      if (fs.existsSync(p)) return p;
    }
  }
  return undefined; // let playwright try its own default
}

function sh(cmd) { return execSync(cmd, { encoding: 'utf8' }); }
function ssh(remoteCmd) {
  // single-quote the remote command so the LOCAL shell doesn't expand remote
  // loop vars ($u/$f/$o) before ssh sends them; escape any embedded quotes
  const quoted = "'" + remoteCmd.replace(/'/g, "'\\''") + "'";
  return sh(`ssh -o ConnectTimeout=10 -o BatchMode=yes ${SSH} ${quoted}`);
}
function mklogin(name, isMod) {
  const out = ssh(`bbb-mklogin ${isMod ? '-m' : ''} -M ${MEETING} -e never '${name}'`).trim();
  return out.replace(/^https?:\/\/[^/]+/, `https://${HOST}`); // bbb-mklogin emits the NAT hostname
}
function apiUrl(action, params) {
  const q = new URLSearchParams(params).toString();
  const checksum = crypto.createHash('sha256').update(action + q + SECRET).digest('hex');
  return `https://${HOST}/bigbluebutton/api/${action}?${q}&checksum=${checksum}`;
}
async function endMeeting(reqCtx) {
  // tearing the meeting down kicks the clients; otherwise browser.close()'s
  // abrupt disconnect leaves them lingering in getMeetings until BBB times them
  // out, keeping the meeting (and its moderator) alive
  try {
    const xml = await (await reqCtx.get(apiUrl('getMeetings', {}))).text();
    for (const block of xml.split('<meeting>').slice(1)) {
      const name = (block.match(/<meetingName>([^<]*)<\/meetingName>/) || [])[1];
      const id = (block.match(/<meetingID>([^<]*)<\/meetingID>/) || [])[1];
      if (name === MEETING && id) {
        await reqCtx.get(apiUrl('end', { meetingID: id, password: 'mp' }));
        console.log(`# ended meeting ${MEETING}`);
      }
    }
  } catch (e) { console.log('# (could not end meeting: ' + e.message + ')'); }
}
function cleanupDesktops() {
  // strictly scoped to this test's users; never touches other desktops/locks
  const us = allUsers.join(' ');
  ssh(`for u in ${us}; do sudo loginctl terminate-user $u 2>/dev/null; sudo pkill -KILL -u $u 2>/dev/null; ` +
      `sudo rm -f /run/vnc/$u /run/vnc/.$u.spawnlock; done; ` +
      `for f in /tmp/.X*-lock; do [ -e "$f" ] || continue; o=$(stat -c %U "$f" 2>/dev/null); ` +
      `for u in ${us}; do [ "$o" = "$u" ] && sudo rm -f "$f"; done; done; true`);
}

// page.evaluate() has no timeout; on a starved/dead renderer it hangs forever.
// Race it so a hang throws (and the moderatorShare retry can recover) instead.
function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, rej) => setTimeout(() => rej(new Error(`${label} timed out after ${ms}ms`)), ms)),
  ]);
}
const evalClick = (page, fn, label) => withTimeout(page.evaluate(fn), 8000, label);

// NOTE: page.waitForFunction(fn, arg, options) -- the options object MUST come
// third; waitForFunction(fn, {timeout}) treats {timeout} as the function ARG and
// silently falls back to the 30s default. Always pass `undefined` for arg.
async function dismissAudioModal(page) {
  // BBB pops a "How do you want to join audio?" modal on join; its overlay
  // intercepts clicks on the action bar until dismissed. "Listen only" closes
  // it without an echo test. Wait for it (it can lag under load), click it,
  // then confirm the overlay actually clears. Harmless if it never appears.
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
  } catch (e) { /* modal never showed; fine */ }
}

async function join(browser, name, url, isMod) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'load', timeout: 45000 });
  // role-agnostic "joined" signal: the meeting name appears in the title once
  // the client is graphql-connected -> the user is a getMeetings attendee,
  // which is what authorizes their /vnc. (Viewers don't all have the Actions
  // button, so don't wait on that for students.)
  await page.waitForFunction((mtg) => document.title.includes(mtg), MEETING, { timeout: 45000 })
    .catch(() => {});
  await dismissAudioModal(page);
  if (isMod) {
    await page.waitForSelector('button[data-test="actionsButton"]', { timeout: 30000 }).catch(() => {});
  }
  console.log(`#   joined ${name}`);
  return { ctx, page, name };
}

async function moderatorShare(page) {
  // under load the moderator UI can lag; wait for it to be ready rather than
  // assuming, and clear any audio modal that re-appeared
  await dismissAudioModal(page);
  // gate on existence, not visibility: an audio overlay may still cover the
  // button, but the evaluate-click below drives the DOM element directly and
  // doesn't care about visibility/interception
  await page.waitForFunction(() => !!document.querySelector('button[data-test="actionsButton"]'), undefined, { timeout: 45000 });
  // The actions dropdown is flaky under load (it can open-then-close, or the
  // audio overlay swallows the open). Retry the whole open->pick->fill->share
  // sequence a few times rather than failing on the first miss.
  for (let attempt = 1; attempt <= 5; attempt++) {
    try {
      await dismissAudioModal(page);
      await evalClick(page, () => document.querySelector('button[data-test="actionsButton"]').click(), 'actions-open');
      await page.waitForFunction(() => [...document.querySelectorAll('[role="menuitem"],li,button')]
        .some(e => /Share a remote desktop/i.test(e.textContent)), undefined, { timeout: 7000 });
      await evalClick(page, () => {
        const it = [...document.querySelectorAll('[role="menuitem"],li,button')]
          .find(e => /Share a remote desktop/i.test(e.textContent));
        it.click();
      }, 'share-item');
      await page.waitForFunction(() => [...document.querySelectorAll('.ReactModal__Content')]
        .some(m => /Remote Desktop URL/i.test(m.textContent)), undefined, { timeout: 7000 });
      const ok = await withTimeout(page.evaluate((host) => {
        const rd = [...document.querySelectorAll('.ReactModal__Content')]
          .find(m => /Remote Desktop URL/i.test(m.textContent));
        if (!rd) return false;
        const inp = rd.querySelector('input[type="text"],input:not([type])');
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(inp, 'wss://' + host + '/vnc');           // collaborate path, not /proxy/
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        const share = [...rd.querySelectorAll('button')].find(b => b.textContent.trim() === 'Share');
        if (!share || share.disabled) return false;
        share.click();
        return true;
      }, HOST), 8000, 'share-fill');
      if (ok) return true;
    } catch (e) {
      console.log(`#   (share attempt ${attempt} failed: ${e.message.split('\n')[0]}; retrying)`);
      await page.keyboard.press('Escape').catch(() => {});   // close a stuck dropdown/modal
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  return false;
}

function studentsUp() {
  const ls = ssh('ls /run/vnc/ 2>/dev/null');
  return new Set(students.filter(s => new RegExp('^' + s + '$', 'm').test(ls)));
}
function wedgedLocks() {
  return ssh(`for u in ${students.join(' ')}; do f=/run/vnc/.$u.spawnlock; ` +
    `[ -e "$f" ] && sudo fuser "$f" >/dev/null 2>&1 && echo $u; done; true`).trim();
}

// Snapshot the server-side state of one stuck user: live spawn processes, who
// holds the spawn lock (and for how long), the per-display log, and the user's
// session journal -- where a machinectl-shelled gnome/Xvnc death/hang logs its
// error (NOT the ~/.vnc log, which is why those come back 0 bytes).
function captureState(u) {
  return ssh([
    `u=${u}`,
    `echo "  -- $u --"`,
    `ps -eo user:20,pid,etimes,cmd | awk -v U="$u" '$1==U' | grep -E "[X]tigervnc|[m]achinectl|[g]nome-session|[t]igervncserver" | head -4 || echo "    (no live spawn procs for $u)"`,
    `f=/run/vnc/.$u.spawnlock; if [ -e "$f" ]; then echo "    spawnlock holders:"; sudo lsof "$f" 2>/dev/null | awk 'NR>1{print "      "$2" "$4" elapsed="}'; else echo "    (no spawnlock)"; fi`,
    `l=$(sudo ls -1t /home/$u/.vnc/*:*.log 2>/dev/null | head -1); echo "    log: \${l##*/} ($([ -n "$l" ] && sudo wc -c < "$l" || echo 0)B)"; [ -n "$l" ] && sudo tail -3 "$l" 2>/dev/null | sed 's/^/      /'`,
    `uid=$(id -u "$u" 2>/dev/null); if [ -n "$uid" ]; then echo "    session journal (_UID=$uid):"; sudo journalctl _UID="$uid" --since "8 min ago" --no-pager 2>/dev/null | tail -6 | sed 's/^/      /'; fi`,
    `echo "    bbb-vnc-collaborate journal:"; sudo journalctl -u bbb-vnc-collaborate --since "8 min ago" --no-pager 2>/dev/null | grep -iw "$u" | tail -4 | sed 's/^/      /'`,
  ].join('\n'));
}

// Classify WHY a stuck spawn died. The display-collision signature
// ("(EE) Server is already active for display N" / "is taken because of
// /tmp/.X*-lock") lives in the bbb-vnc-collaborate SERVICE journal and is keyed
// by the tigervncserver PID, NOT the username -- so correlate via this user's
// "Log file is /home/$u/.vnc/...:N.log" lines (which DO carry the username) to
// the same PID's collision lines. (This is the bit that was missed before:
// grepping the 0-byte ~/.vnc log, or the journal by username, never sees it.)
function classifyWedge(u) {
  return ssh([
    `u=${u}`,
    `J=$(sudo journalctl -u bbb-vnc-collaborate --since "15 min ago" --no-pager 2>/dev/null)`,
    `pids=$(printf '%s\\n' "$J" | grep -F "Log file is /home/$u/.vnc" | sed -nE 's/.*python3\\[([0-9]+)\\].*/\\1/p' | sort -u)`,
    `disp=$(printf '%s\\n' "$J" | grep -F "Log file is /home/$u/.vnc" | grep -oE ':[0-9]+\\.log' | grep -oE '[0-9]+' | sort -u | tr '\\n' ' ')`,
    `hit=""`,
    // classify on the FATAL "already active for display" (the lost bind); the
    // "is taken because of /tmp/.X*-lock" warnings are the RECOVERABLE case (the
    // spawn skipped to a free display and succeeded), so they're context, not the
    // verdict.
    `for p in $pids; do printf '%s\\n' "$J" | grep -E "python3\\[$p\\]:" | grep -iqE "already active for display" && hit=yes; done`,
    `if [ -n "$hit" ]; then`,
    `  echo "    CAUSE: DISPLAY-NUMBER COLLISION (Bug 2) on display(s) \${disp:-?} -- Xvnc hit the FATAL 'Server is already active for display'; gnome then could not open the display. Evidence (fatal + the lock-race warnings that led to it):"`,
    `  for p in $pids; do printf '%s\\n' "$J" | grep -E "python3\\[$p\\]:" | grep -iE "already active for display|is taken because of /tmp/\\.X" | tail -3 | sed 's/^/      /'; done`,
    `else`,
    `  echo "    CAUSE: no fatal display collision for $u -- some other spawn failure (see session journal above)"`,
    `fi`,
  ].join('\n'));
}

// On a wedge, DON'T kill immediately: keep watching for the socket so we can
// tell a merely-slow spawn (it eventually appears -> not a true deadlock) from
// a stuck one (never appears -> apparent deadlock), and capture why.
async function diagnoseWedged(stuck) {
  const secs = parseInt(process.env.RD_DIAGNOSE_SECS || '240', 10);
  console.log(`\n# === DIAGNOSE: ${stuck.length} stuck student(s); watching up to ${secs}s WITHOUT killing ===`);
  console.log('# initial server-side state of each stuck spawn:');
  for (const u of stuck) process.stdout.write(captureState(u));
  const t0 = Date.now();
  const healed = {};
  const pending = new Set(stuck);
  while (pending.size && (Date.now() - t0) / 1000 < secs) {
    await new Promise((r) => setTimeout(r, 5000));
    const up = studentsUp();
    for (const u of [...pending]) {
      if (up.has(u)) {
        healed[u] = Math.round((Date.now() - t0) / 1000);
        pending.delete(u);
        console.log(`#   HEALED: ${u} socket appeared after ${healed[u]}s -> SLOW spawn, not a permanent deadlock`);
      }
    }
  }
  console.log('\n# === DIAGNOSE VERDICT ===');
  for (const u of stuck) {
    if (healed[u] != null) {
      console.log(`#   ${u}: SLOW (healed after ${healed[u]}s) -- the unbounded wait merely held the lock too long`);
    } else {
      console.log(`#   ${u}: STILL STUCK after ${secs}s -> apparent TRUE deadlock.`);
      process.stdout.write(classifyWedge(u));   // collision vs other-failure
      process.stdout.write(captureState(u));     // raw final state
    }
  }
}

(async () => {
  console.log(`# remote-desktop class-start test: ${N} students vs ${HOST} (meeting ${MEETING})`);
  const { chromium, request } = loadPlaywright();
  const reqCtx = await request.newContext({ ignoreHTTPSErrors: true });
  const exe = findChrome();
  console.log(`# chromium: ${exe || '(playwright default)'}`);

  console.log('# cleaning any prior desktops for the test users...');
  cleanupDesktops();

  const browser = await chromium.launch({
    executablePath: exe,
    args: ['--ignore-certificate-errors', '--no-sandbox'],
  });

  let pass = false;
  try {
    console.log('# generating login URLs...');
    const logins = { [MODERATOR]: mklogin(MODERATOR, true) };
    for (const s of students) logins[s] = mklogin(s, false);

    console.log('# joining moderator...');
    const mod = await join(browser, MODERATOR, logins[MODERATOR], true);
    console.log('# joining students (parallel)...');
    await Promise.all(students.map((s) => join(browser, s, logins[s], false)));

    // let every client finish its graphql join + data-channel subscription so
    // the one share fans out to all of them at once
    await new Promise((r) => setTimeout(r, 5000));

    console.log('# moderator sharing wss://' + HOST + '/vnc (one share -> N simultaneous /vnc opens)...');
    const shared = await moderatorShare(mod.page);
    if (!shared) throw new Error('could not complete the Share dialog (selector drift?)');

    const deadline = Date.now() + SPAWN_TIMEOUT_MS;
    let up = new Set();
    while (Date.now() < deadline) {
      up = studentsUp();
      process.stdout.write(`\r#   desktops up: ${up.size}/${N}   `);
      if (up.size >= N) break;
      await new Promise((r) => setTimeout(r, 2000)); // server-side poll; don't depend on the (maybe dead) page
    }
    process.stdout.write('\n');

    const missing = students.filter(s => !up.has(s));
    const wedged = wedgedLocks();
    if (missing.length) console.log(`# MISSING desktops: ${missing.join(' ')}`);
    if (wedged) console.log(`# WEDGED spawn locks (held, never released -- the deadlock): ${wedged}`);
    pass = missing.length === 0 && !wedged;
    console.log(`\nRESULT: ${pass ? 'PASS' : 'FAIL'}  (${up.size}/${N} desktops up, ${wedged ? 'wedged locks present' : 'no wedged locks'})`);

    // RD_DIAGNOSE: before cleanup, watch the stuck spawns long enough to tell
    // a slow spawn from a true deadlock, and capture why they stalled.
    if (process.env.RD_DIAGNOSE && missing.length) await diagnoseWedged(missing);
  } finally {
    await browser.close();
    if (!process.env.RD_KEEP) {
      console.log('# cleaning up: ending meeting + removing test desktops...');
      await endMeeting(reqCtx);   // kicks the clients so they don't linger in getMeetings
      cleanupDesktops();
    } else {
      console.log('# RD_KEEP set: leaving meeting + desktops up.');
    }
    await reqCtx.dispose();
  }
  process.exit(pass ? 0 : 1);
})().catch((e) => { console.error('ERROR:', e.message); process.exit(2); });

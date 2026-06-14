# collaborate tests

Integration tests that exercise the **deployed** collaborate VNC stack by
driving real BigBlueButton clients — not by reproducing its logic.

## `remote-desktop-class-start.cjs`

Tests the desktop-spawn path in `vnc_collaborate/websockify.py`
(`new_websocket_client` → `ensure_vnc_server` → `start_VNC_server`) under the
real class-start condition that exposed two defects (both fixed by
`ensure_vnc_server`):

- **(A) Display-number collision** — when many desktops spawn at once,
  `tigervncserver`'s "lowest free X display" pick races, two spawns grab the
  same `:N`, and the loser dies (`Server is already active for display N`).
- **(B) Spawn-lock deadlock** — `start_VNC_server` waited for the new socket
  with no timeout while the per-user spawn lock was held, so a dead spawn (e.g.
  from A) hung forever holding the lock, permanently black-screening that
  student and stacking every later reconnect behind it.

Original write-up: `~/project/reports/bbb-collaborate-desktop-bugs.md`.

What it does:

1. Joins a moderator + N students into one meeting, each in its own browser
   context (so each has a genuine authenticated session — `/vnc` auth needs the
   user's `JSESSIONID` *and* `sessionToken` from a real login, and the user must
   be a live `getMeetings` attendee; a session token alone gets a 401).
2. The moderator shares a remote desktop **once**, pointed at `wss://HOST/vnc`
   (the collaborate websockify path — *not* the default `wss://HOST/proxy/`,
   which is the unrelated bbb-wss-proxy).
3. That single share fans out over the `remoteDesktop` data channel: every
   client opens `wss://HOST/vnc?sessionToken=<its own>` at the same instant —
   the N simultaneous `ensure_vnc_server` spawns that caused the display-number
   collisions.

Oracle (checked over SSH on the host):

- **PASS** iff every student's persistent socket `/run/vnc/<Student>` appears
  within the timeout **and** no student's `/run/vnc/.<Student>.spawnlock` is left
  wedged — a held spawnlock is the signature of the deadlock (B).
- Unpatched websockify: a lost display race hangs `start_VNC_server` while
  holding the lock → that student never appears and its lock stays wedged →
  **FAIL**. With `ensure_vnc_server` (bounded wait + retry-with-jitter, lock
  always released) every student comes up → **PASS**.

### Running

```bash
node remote-desktop-class-start.cjs [N_STUDENTS]      # default 4
```

Env overrides: `RD_HOST` (default `jammy-300.samsung`), `RD_SSH`
(`ubuntu@jammy-300.samsung`), `RD_MEETING`, `RD_STUDENTS`, `RD_KEEP` (leave
desktops up after the run), `PW_MODULE` / `PW_CHROME` (Playwright module /
chromium binary).

### Requirements

- A running BBB host with the collaborate stack and `bbb-auth-jwt`
  (`bbb-mklogin`), reachable by SSH with sudo (for login URLs and the
  server-side oracle).
- Node Playwright. Browsers in this account predate the pinned revision, so the
  script auto-detects a chromium under `~/.cache/ms-playwright/chromium-*` and
  launches it via `executablePath`; override with `PW_CHROME` if needed.

### Validating a websockify change

Run against the host before the change (baseline) and after deploying the
patched `vnc_collaborate/websockify.py` + restarting `bbb-vnc-collaborate`.
Increase `N_STUDENTS` to raise display-number contention if the race doesn't
trip at the default. Cleanup is strictly scoped to the test users
(`RDTeacher`, `Student01`…), so it never disturbs other desktops.

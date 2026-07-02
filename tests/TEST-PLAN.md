# collaborate remote-desktop test plan

A catalogue of tests we want, in two parts:

1. **Regression tests** — one per bug we've diagnosed (this session and
   earlier), so each fix is pinned and the still-open bugs are tracked.
2. **Feature-coverage tests** — exercise every known remote-desktop feature.

Status legend: **[EXISTS]** implemented · **[NEW]** to write · **[UNFIXED]**
the bug is not yet fixed — the test documents desired behaviour and would fail
today · **[HARD]** needs a non-obvious oracle (visual/timing/fault-injection).

## Testing approach

Build on the existing harness, `tests/remote-desktop-class-start.cjs`:
Node + Playwright drive **real** BBB clients (moderator + N students, each a
genuine authenticated session — `/vnc` auth needs the user's `JSESSIONID` *and*
`sessionToken` and the user must be a live `getMeetings` attendee), and the
oracle is checked **server-side over SSH** (inspecting `/run/vnc/`, processes,
X state). Default target `jammy-300.samsung`; scoped test users so runs never
disturb other desktops.

Four layers, each with a natural oracle:

| Layer | What | Oracle |
|-------|------|--------|
| **Spawn / websockify** | `ensure_vnc_server`, sockets, locks, perms | SSH: `/run/vnc/*`, `ss -xlp`, spawnlocks, `ls -l` group/mode |
| **fvwm teacher grid** | geometry, zoom, toggle, desktop name | SSH + X tools on `:N`: `xrandr`, `xdotool`, `xwininfo`, `import`, `ps` |
| **BBB plugin UI** | share, lock, buttons, labels, versions | Playwright: DOM, user-list labels, noVNC canvas, `clientSessionUUID` |
| **End-to-end** | a class actually works | combination |

Prefer **server-side state assertions** over pixel diffs. A shared fixture
(extracted from the existing harness) should provide: create meeting → join
moderator+students with real auth → share remote desktop → SSH helpers (list
`/run/vnc` with group/mode, `ps` filters, current fvwm desktop, display
geometry, window tree, current RFB desktop name).

### Architecture the tests must respect

- **Outer vs inner VNC.** `browser noVNC ─/vnc ws─► websockify handler (outer,
  ephemeral) ─► inetd teacher/student_desktop Xvnc ─► ssvncviewer ─►
  /run/vnc/USER (inner, persistent)`. Inner crash → ssvncviewer retry
  reconnects, **no reload needed**; outer wedged in the spawn lock → **needs a
  reload**. Regression tests should cover *both* — the outer wedge is the
  production deadlock.
- **noVNC ~50 s connect timeout.** A `/vnc` socket with no data for ~50 s is
  closed by noVNC; expect ~50 s latency between a failed spawn and the browser
  giving up. Zombie websockify handlers can keep holding the flock until reaped.
- **Plugin has no auto-reconnect.** Reconnect happens only via `reconnectCounter`
  (layout re-entry after a screenshare), the manual Reconnect button, or a
  re-share. A full page reload regenerates `clientSessionUUID`.

---

## Part 1 — Regression tests

### A. Spawn / websockify (server-side)

- **A1 — Display-number collision at class start** **[EXISTS]** — N students
  spawn at once; every `/run/vnc/<Student>` appears, no `Server is already
  active for display N` loser. Signature lives in the **service journal**
  (`systemctl status bbb-vnc-collaborate`), not the 0-byte `~/.vnc/HOST:N.log`.
- **A2 — Spawn-lock deadlock** **[EXISTS]** — after mass spawn, no wedged
  `/run/vnc/.<Student>.spawnlock` (a held write-lock = the deadlock signature);
  every student up within the 20 s bound. *(Bounded wait + release + jitter in
  `ensure_vnc_server`.)*
- **A3 — Orphaned socket / double-spawn** **[NEW]** — repeated/concurrent
  connects for one user never leave a kernel listener whose fs path is missing;
  the `fcntl.flock` spawnlock serialises.
- **A4 — Socket group / mode** **[NEW]** — every spawned `/run/vnc/<user>` is
  `mode 0660 group=bigbluebutton`. A mis-grouped socket (`0600 …:user`) makes
  the grid's `os.access(R_OK)` silently skip the cell → "missing students".
  *(Bug 7; guard the chgrp in every spawn path.)*
- **A5 — Persistent Xvnc survives reload** **[NEW]** — reload the panel; the
  persistent socket and gnome-session survive (same inode/PID).
- **A6 — Resource desktop after host reboot** **[NEW/UNFIXED]** — a resource
  desktop (e.g. `WindowsServer2022`, no human to trigger a connection) appears
  in the grid after a host reboot. *(Bug 6 — no boot-time spawn trigger yet;
  currently fails.)*
- **A7 — Blank share** **[NEW — could not reproduce in normal use]** — share →
  unshare → re-share; the share must connect the outer session to the inner
  desktop. *(Bug 9. Harness: `tests/a7-blank-second-share.cjs`, verified working
  2026-07-01.* **Finding:** on the current build (plugin `658ff7b`,
  vnc-collaborate `184327`) **3/3 sequential shares connected** — the outer
  inetd spawn even skipped a busy `:2` to take `:3` and still connected. The one
  blank observed earlier was against a **3.6h-stale *leaked* `:2`** (a test
  artifact), i.e. an abnormal/stale display state, not normal contention. So A7
  is **not an active bug in normal share/unshare** here.
  *Latent risk (not triggered):* the outer inetd spawn (`websockify.py:407-413`)
  is a bare `socat`/`tigervncserver -inetd` Popen with **no `ensure_vnc_server`
  collision-retry** (the persistent-desktop `:376` and screenshare `:432` paths
  have it). It skips normal occupied displays fine, but a stale/corrupt display
  (e.g. a leaked session's lock) can still wedge it → blank. Worth hardening for
  robustness; keep the harness as a regression guard.)*

### B. Teacher grid — Set Geometry (this session)

- **B1 — Set Geometry does not black-screen** **[NEW]** — pick each menu
  resolution; `VNC-0` stays **connected** at the requested size (never
  `disconnected`), framebuffer not blank. *(Guards `--output VNC-0 --off`.)*
- **B2 — Non-preset geometry (1600×900)** **[NEW]** — a matching mode is
  created and the output is driven at it.
- **B3 — Idempotent modes** **[NEW]** — repeating the same geometry leaves
  exactly **one** mode of that name (no `newmode` pileup).
- **B4 — Return to the grid after resize** **[NEW]** — after Set Geometry from
  grid, `xdotool get_desktop == 1` and grid mouse bindings are active.
  *(Guards the desk-0 dump.)*
- **B5 — No 5-second stall entering own desktop after resize** **[NEW]** —
  grid→own toggle completes < ~1.5 s and the own-desktop viewer window appears.
  *(Guards the `TigerVNC`-only wait-loop.)*

### C. Teacher grid — zoom / toggle / desktop name (this session)

- **C1 — Grid button exits a scaled (ssvncviewer) zoom** **[NEW]** — returns to
  grid **and the viewer process terminates** (no lingering `ssvncviewer …
  Zoomed Student Desktop`). *(Guards `windowclose`→`windowkill`.)*
- **C2 — Grid button exits a 1:1 (xtigervncviewer) zoom** **[NEW]**.
- **C3 — "Grid" label appears promptly on return** **[NEW]** — after
  grid→own→grid with a scaled viewer, the moderator user-list label reads
  **"Grid"** within ~2 s (not >10 s / never). *(Guards the windowkill fix.)*
- **C4 — No stale "Grid" label on own desktop** **[NEW]** — own-desktop label
  is blank; a killed viewer never re-sets "Grid" later.
- **C5 — Scaled zoom uses `-x11cursor`** **[NEW]** — assert the ssvncviewer
  cmdline; single-cursor visually is **[HARD]**. *(Double-cursor fix.)*
- **C6 — Escape sequence is gone** **[NEW]** — scaled zoom launched with
  `-escape never`; the grid button is the sole exit. *(Alt-Shift-Q removal.)*

### D. BBB plugin / version regressions (UI)

- **D1 — sessionToken across BBB versions** **[NEW]** — the plugin resolves the
  session token (URL → `sessionStorage['BBB_sessionToken']` → SDK) and connects
  on **3.0.27 / 3.0.29 / 3.0.30 / 3.0.31** — no `sessionToken=undefined` → 401
  → blank. *(Bug 4.)*
- **D2 — Stale manifest after plugin upgrade** **[NEW]** — upgrading the plugin
  on a **live** meeting then reloading fails to load (old bundle hash 404 — the
  *expected* failure); after end+recreate (or `bbb-conf --restart`) it loads.
  *(Bug 5 — documents the operational rule.)*
- **D3 — No client double-websocket** **[NEW]** — share / content-return opens
  a single `/vnc` websocket, no double-spawn. *(needs the `hasEverShownContent`
  gate.)*
- **D4 — Reconnect paths** **[NEW]** — after a screenshare removes and re-adds
  our content, `reconnectCounter` bumps and the desktop comes back; the manual
  Reconnect button works.

### E. Rendering / crashes (earlier sessions)

- **E1 — libXft crash on reshare** **[NEW/HARD]** — mass grid reshare does not
  SIGSEGV the viewer in libXft (segfault at offset `0x18` in
  `XftFontUnloadGlyphs`, fixed in **libXft ≥ 2.3.6**). Oracle: no `segfault …
  libXft` in `dmesg`, grid cells still render. *(Bug 3 — the 2.3.6 backport is
  in the apt repo and installed on collaborate.freesoft.org; verify itpietraining
  when it next wakes. Should-pass regression guard.)*
- **E2 — dash-to-panel menu bar present** **[NEW]** — a fresh desktop is not
  blank gnome: `disable-user-extensions=false` and the bottom panel renders.
- **E3 — Teacher's own desktop not black** **[NEW]** — own-desktop view renders
  while students are up.

### F. Tunneled cross-server desktops (earlier)

- **F1 — Tunneled desktop appears** **[NEW]** — `/run/vnc/USER@HOST` present,
  owned `LOCAL_USER:bigbluebutton`, kernel listener is `ssh`; cell in the grid.
- **F2 — Survives hibernate/reconnect** **[NEW]** — remote user has
  `enable-linger`; `vnc-tunnel@` clears its stale socket on restart, no
  restart-loop.
- **F3 — Interactive** **[NEW]** — click-to-zoom works on a tunneled cell.

### G. Packaging (earlier)

- **G1 — pyjavaproperties upgrade** **[NEW]** — `apt upgrade` of
  `python3-bigbluebutton` does not fail on the `pyjavaproperties.py` overwrite.
- **G2 — dash-to-panel install** **[NEW]** — a fresh install ends up with
  dash-to-panel present (it must be a real apt **dependency**, not installed
  from a postinst — apt holds the dpkg lock). *(Bug 10.)*

---

## Part 2 — Feature coverage

### H. Grid basics
- **H1** grid renders all connected student desktops (Hollywood Squares).
- **H2** grid button toggles grid ↔ own desktop, both directions.
- **H3** grid updates as students join / leave.
- **H4** Max Grid Size menu (2×2 … 5×5) changes the layout.
- **H5** Page Number pagination when students exceed one page.
- **H6** Display Mode (All Desktops / Current Meeting) filters the grid.

### I. Zoom / interact
- **I1** click a student → fully interactive zoom (keyboard + mouse reach it).
- **I2** right-click → "View this desktop" → view-only (no control).
- **I3** own-desktop zoom via the grid button.
- **I4** viewer selection: ssvncviewer when `scale ≠ 1`, xtigervncviewer at 1:1.

### J. Screenshare
- **J1** screenshare a chosen desktop (teacher or student) → it projects to
  every other desktop.
- **J2** screenshare indicator: colored rect + "End screenshare" button.
- **J3** ending the screenshare removes the projection everywhere.

### K. Audio (deaf / undeaf)
- **K1** "Deaf all viewers" deafs viewers (not moderators); deaf icons show.
- **K2** selective deaf via right-click.
- **K3** zooming a student undeafs them; returning to grid re-deafs (only if
  they were deafed).

### L. Clipboard
- **L1** "Enable clipboard" toggle.
- **L2** cut-and-paste teacher ↔ student at 1:1 (xtigervncviewer).
- **L3** documented limitation: no cut-and-paste with the scaling viewer — assert
  the expected absence.
- **L4** browser→VNC and VNC→browser directions.

### M. Desktop-name label
- **M1** "Grid" while in grid mode · **M2** student name while viewing a student
  · **M3** screenshared user's name reflected (the `1056f8d` fix) · **M4** blank
  on own desktop · **M5** label visible to moderators only (channel targeting).
- **M6 — student rows update during screenshare** **[NEW]** — when a
  screenshared student switches apps, their moderator-grid label updates (not
  frozen at connect-time). *(Bug 8 — fixed since the earlier report by `1056f8d`
  server-side + plugin `658ff7b` "deliver desktopMode entry back to its
  non-moderator creator", both deployed; this verifies it and guards regression.)*

### N. Plugin plumbing
- **N1** moderator "share remote desktop" fans out to all viewers.
- **N2** viewOnly gating by `operators` (all / moderators / presenter / me).
- **N3** lock / unlock controls.
- **N4** configurable keysym buttons send their keysym (e.g. F22 grid toggle).
- **N5** fullscreen button.

### O. Student side
- **O1** student desktop spawns on connect; the student sees their own
  persistent desktop.
- **O2** the student's fullscreen viewer has no escape / menu key
  (`-MenuKey=None`) — a student can't break out.

---

## Notes

- **Harness reuse.** Extract the meeting-join + share + SSH-oracle plumbing from
  `remote-desktop-class-start.cjs` into a shared module so each spec is thin.
  `RD_DIAGNOSE` mode (watches wedges up to 240 s, dumps the journal, classifies
  collisions) is a model for the spawn tests.
- **Two tiers.** Fast server-side checks (spawn, geometry, windowkill, labels,
  socket perms) run in seconds on jammy-300; full-UI Playwright specs are slower
  — keep them separate so the fast tier can gate every change.
- **[UNFIXED] items** — only **A6** (resource-desktop-after-reboot) and **A7**
  (blank-second-share) are genuinely open; writing them now turns "known bug"
  into "tracked failing test". (E1 libXft and M6 student-label were both fixed
  and deployed since the earlier reports — kept as should-pass regression guards.)
- **Open problem, not yet root-caused:** grid windows in wrong positions after
  churn — worth a characterization test, gated off CI until diagnosed.
- **[HARD] oracles:** cursor rendering, libXft crash, clipboard round-trip need
  pixel capture (`import` + compare) or fault injection; scope separately.

## Source reports (per bug, for whoever writes the tests)

- `~/project/reports/bbb-collaborate-desktop-bugs.md` — A1/A2 (deadlock,
  collision), E1 (libXft), A4 (socket group)
- `~/project/reports/bbb-desktop-deadlock-recovery-and-reload-proof.md` —
  outer/inner model, ~50 s timeout, reload proof
- `~/project/reports/bbb-3.0.30-sessiontoken-plugin-regression.md` — D1, D2
- `~/project/reports/bbb-windows-grid-desktop-reboot.md` — A6, A4
- `~/project/reports/bbb-dash-to-panel-report.md` — G2
- `~/project/reports/bbb-desktop-name-indicator-report.md` — M1–M6
- This session's commits (black-screen, return-to-grid, 5 s-stall, escape,
  x11cursor, windowkill) — B*, C*

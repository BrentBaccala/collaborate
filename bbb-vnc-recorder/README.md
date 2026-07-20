# bbb-vnc-recorder

A per-meeting recorder for the collaborate server-side VNC desktops. It
records every meeting participant's persistent Xtigervnc desktop to a raw-RFB
container (**FBSX**), **only while two gates both hold**, keyed on the UNIX
username, on a single epoch-ms clock.

This package is **record-only**: it produces the raw source-of-truth files.
Transcoding those to video / building a playback UI is a separate future
deliverable and is intentionally out of scope here.

## The two gates

The recorder records a meeting's desktops only when **BOTH** are true:

1. **The meeting's recording is *active* (not paused).** Driven by the
   akka-apps event `RecordingStatusChangedEvtMsg`, whose body carries a
   `recording` boolean — **true on record Start/Resume, false on Pause/Stop**.
   akka broadcasts it (default case in `FromAkkaAppsMsgSenderActor`) on the
   same `from-akka-apps-redis-channel` the recorder already subscribes to for
   gate 2, so one subscriber (`AkkaEventWatcher`) tracks both gates.

   > **Why not the `getMeetings` `<recording>` flag?** In BBB the moderator's
   > "Stop Recording" button is a **pause**, not a stop: recording is captured
   > as start/pause/resume *segments*, and `getMeetings` reports
   > `recording=true` continuously from the first Start until the meeting ends
   > — it **stays true across every pause**. So that flag can only tell you the
   > meeting *is being recorded at all*, never that it is *paused right now*.
   > Only `RecordingStatusChangedEvtMsg` reflects the real active/paused state,
   > so gate 1 is event-driven. The `getMeetings` poll is still used to
   > enumerate meetings and their participant lists.

   **Startup seeding (and its limitation).** Redis pub/sub does not replay past
   events, so a recorder started mid-meeting won't have seen the record-Start.
   On first sight of a meeting, gate 1 is *seeded best-effort* from the
   `getMeetings` `<recording>` flag; the first real `RecordingStatusChangedEvtMsg`
   thereafter is authoritative and overrides the seed. Because the seed source
   cannot distinguish "recording" from "paused", **a recorder that starts while
   a meeting is paused will seed gate 1 true and record until the next
   pause/resume event corrects it.** This only affects the window between
   recorder start and the next recording event; steady-state pause/resume is
   exact.

2. **A remote-desktop share is active.** Detected from the
   `bbb-plugin-remote-desktop` plugin's persistEvents. The plugin emits
   `remote-desktop-share-start` when a moderator shares a desktop and
   `remote-desktop-share-stop` when they stop; akka-apps re-broadcasts these
   as `PluginPersistEventEvtMsg` on the `from-akka-apps-redis-channel` Redis
   channel, which the recorder subscribes to. (This requires the plugin's
   `manifest.json` to carry `"eventPersistence": { "isEnabled": true }` —
   shipped in `bbb-plugin-remote-desktop` ≥ 0.3.0-16. Because manifests are
   fetched at meeting-create, a **fresh meeting** is needed to pick it up.)

When either gate drops (e.g. a **record pause**), the meeting's per-desktop
recorders stop and **finalize** their current segment; the meeting session
object is *kept* so its segment counter survives. When both gates come back
(e.g. **resume**), recording continues in a fresh numbered segment (see
[Segments](#segments-pause--resume--reconnect)), never overwriting the paused
one. The session is torn down only when the meeting actually ends.

> The plugin "Share a remote desktop" **URL** is *not* a recording key — one
> URL is fanned out by `bbb-wss-proxy` to every participant's own
> `/run/vnc/<user>`. The recorder keys on the UNIX username, never the URL.

## The join key: UNIX username

Every collaborate participant has a persistent server-side desktop:

```
Xtigervnc :N -rfbunixpath /run/vnc/<UNIXuser> -rfbport 590N \
             -SecurityTypes None -geometry 1280x1024 -depth 24
```

The **UNIX username** is the stable identity that joins the desktop socket
(`/run/vnc/<user>`), the BBB participant (`fullName` →
`vnc_collaborate.users.fullName_to_UNIX_username`, i.e. spaces squashed), and
the grid-mode screenshare index. The recorder enumerates the recorded
meeting's participants, maps each to a UNIX user, and records the
`/run/vnc/<user>` sockets that exist — starting/stopping per-desktop
recorders as participants join and leave.

A shared-mode RFB connect does **not** disturb the live user.

## What gets recorded

Per meeting, under `storage.directory/<internalMeetingID>/`:

| File | Contents |
|------|----------|
| `<unix_user>.<n>.fbsx`      | raw-RFB recording of segment *n* of that user's desktop (see below) |
| `<unix_user>.<n>.fbsx.json` | sidecar: identity + format metadata (+ finalize fields) |
| `screenshare.jsonl`         | grid-mode projection index (see below) |

Each desktop is recorded as one or more **segments** — `<user>.1.fbsx`,
`<user>.2.fbsx`, … — one self-contained FBSX per recording run. A new segment
begins whenever recording resumes after a pause, or after a mid-session
connection drop is re-established (see below). Segments are ordered by their
sidecar `start_epoch_ms`.

**No audio.** Audio stays with BBB's own recorder and is aligned later via the
shared epoch-ms clock.

### FBSX container format

`FBSX0001` stores the raw server→client RFB byte stream, teed exactly as
`recv()` delivered it, each chunk stamped with a `CLOCK_REALTIME` epoch-ms
timestamp. **Nothing is decoded at capture time** — the recorder performs the
RFB 3.8 handshake, negotiates a compact encoding + a fixed 32bpp pixel format,
drives incremental `FramebufferUpdateRequest`s on a timer, and tees whatever
bytes the server sends.

```
magic:  b"FBSX0001\n"                        (9 bytes)
record: u32be length, u64be epoch_ms, <length raw server->client bytes>   (repeated)
```

The stream is teed from the very first byte (the RFB `ProtocolVersion`), so a
decoder can replay the whole session — handshake included — straight out of
the file.

- **Encoding:** `Tight` by default (config `recording.encoding`, also `zrle`
  or `raw`). The recorder never decodes, so it stores whatever the server
  sends; requesting Tight shrinks the stored bytes ~10–50× vs Raw (a static
  800×1024 desktop's initial frame drops from ~2 MB to a few KB). The
  **Cursor** pseudo-encoding is deliberately **not** requested, so the cursor
  is baked into the framebuffer. `DesktopSize`/`LastRect` pseudo-encodings are
  advertised and handled by the decoder.
- **Pixel format:** 32bpp / depth-24 truecolor, little-endian, red-shift 0 /
  green-shift 8 / blue-shift 16 (matches noVNC). A Raw pixel is `[R,G,B,pad]`;
  a Tight `TPIXEL` is `[R,G,B]`.

Sidecar `<file>.json` fields: `format`, `start_epoch_ms`, `geometry`,
`pixel_format`, `encoding`, `rfb_version`, `desktop_name`, `unix_user`,
`meeting_id`, `segment`, `rfbport`. On finalize (any exit) the recorder also
writes `end_epoch_ms`, `duration_ms`, `bytes_recorded`, and `exit_reason`
(one of `stopped`, `eof: …`, `send-failed: …`, `error: …`, or `unknown`).

### Segments (pause / resume / reconnect)

Each per-desktop recorder opens its FBSX file with `wb` (an FBSX is a *single*
continuous RFB session — handshake included — so a decoder replays it as one
stream; you cannot concatenate two sessions into one file). To keep every run
self-contained **and** never lose earlier data, each (re)start writes a **new
numbered part file** `<user>.<n>.fbsx`:

- **Pause → resume:** on gate-1 pause the recorder stops and finalizes segment
  *n* (`exit_reason=stopped`); on resume it starts segment *n+1*. The segment
  counter lives on the meeting session and survives the pause.
- **Mid-session connection drop:** if the desktop socket dies, the recorder
  exits with a logged reason (`eof: …` when the server closes the socket,
  `send-failed: …` when the outgoing `FramebufferUpdateRequest` errors — this
  path used to be a *silent* `break`) and finalizes the segment. The next 5 s
  reconcile restarts a fresh segment against the same desktop. The bytes
  captured before the drop are preserved in the earlier part file — a restart
  **never truncates** a prior segment.

Every recorder exit — clean stop, EOF, send failure, or unexpected error —
logs a one-line `finished recording <user> -> <file> (<dur>s, <bytes>B,
reason=<…>)` and stamps the finalize fields into the sidecar, so a
(non-)recording is diagnosable from the log + sidecar alone.

### Screenshare index

A `LISTEN vnc_screenshare` thread on the collaborate Postgres DB captures
grid-mode teacher projections (`project_to_students` writes
`vnc_screenshare("meetingId", screenshare=<UNIXuser>)` + `NOTIFY`). The NOTIFY
carries no payload, so each notification triggers a table snapshot + diff;
every `start` / `switch` / `stop` transition is appended to the meeting's
`screenshare.jsonl` as `{epoch_ms, action, screenshare_user, meeting_id}`.
This is the *projection index*, not a gate.

> The `vnc_screenshare` table's `meetingId` is the value the desktops use
> (`MeetingId` env). The indexer routes an event to a session directory when
> that id matches the session's internal or external id, else it falls back to
> a directory named by the raw id so nothing is lost.

## Single clock, cross-stream sync

All per-desktop recorders and the screenshare index run on one host and use
one `CLOCK_REALTIME` epoch-ms clock, so aligning any two streams (or a stream
against BBB's audio recording) is a direct timestamp comparison. Validated:
two independent recorders on one desktop stamped the same visual events at
0-ms A-B skew.

## Decoding / verifying a recording

`fbsx-decode` (`/usr/bin/fbsx-decode`) replays an FBSX file, reconstructs the
raw RFB stream, decodes framebuffer updates (Raw, CopyRect, Tight,
DesktopSize, LastRect), and writes the final framebuffer as a PPM — proving
the stored bytes reproduce the desktop pixels. The Tight decoder is a faithful
port of noVNC's `decoders/tight.js`.

```
fbsx-decode /var/lib/bbb-vnc-recorder/<meeting>/<user>.1.fbsx --ppm /tmp/frame.ppm
```

(JPEG-compressed Tight rects need `python3-pil` to fully decode; without it
those rects are skipped, everything else still decodes.)

## Configuration

`/etc/bbb-vnc-recorder/config.yml` (all keys optional; defaults shown in the
shipped file): `storage.directory`, `redis.{host,port,password,channels}`,
`postgres.{host,dbname,user,password}`,
`recording.{encoding,fps,poll_interval}`, `vnc.run_dir`, `plugin.*`.

## Service

`bbb-vnc-recorder.service` — a standalone `Type=simple` systemd unit running
`/usr/bin/bbb-vnc-recorder` as root (needs to read every user's
`/run/vnc/<user>` socket and write under `/var/lib/bbb-vnc-recorder`). Enabled
on install but **not** auto-started; start it once Redis / Postgres / BBB are
configured:

```
sudo systemctl start bbb-vnc-recorder
```

## Building

```
./build.sh          # FPM deb, version derived from git timestamp
```

Depends: `python3, python3-redis, python3-psycopg2, python3-yaml,
python3-bigbluebutton`.

## Tests

- `tests/test_gates.py` — gate-1 (`RecordingStatusChangedEvtMsg`) and gate-2
  message classification, the pause/resume transition sequence, best-effort
  startup seeding + event-override, and screenshare diffing (no broker needed).
- `tests/test_fbsx_roundtrip.py` — records a throwaway Xtigervnc desktop with
  Tight *and* Raw, decodes both, asserts the frames are byte-identical and
  Tight is materially smaller (auto-skips if Xtigervnc is absent).
- `tests/test_finalize.py` — records a throwaway Xtigervnc desktop and asserts
  every exit path finalizes the sidecar (`end_epoch_ms`/`duration_ms`/
  `bytes_recorded`/`exit_reason`) and logs a finish summary; that a server that
  vanishes mid-recording exits with a non-silent reason; and that a drop +
  restart writes a fresh `<user>.<n>.fbsx` segment without truncating the prior
  one (auto-skips if Xtigervnc is absent).

See `~/project/reports/bbb-vnc-recorder.md` for the validation write-up
(what was proven locally vs. what still needs a live grid-mode BBB).

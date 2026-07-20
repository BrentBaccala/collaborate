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

1. **The meeting is being recorded.** Detected from the BBB API:
   `getMeetings()` / `getMeetingInfo`'s `<recording>` flag, polled every
   `recording.poll_interval` seconds (via `python3-bigbluebutton`'s
   `bigbluebutton.py`). The same poll yields the participant list.

2. **A remote-desktop share is active.** Detected from the
   `bbb-plugin-remote-desktop` plugin's persistEvents. The plugin emits
   `remote-desktop-share-start` when a moderator shares a desktop and
   `remote-desktop-share-stop` when they stop; akka-apps re-broadcasts these
   as `PluginPersistEventEvtMsg` on the `from-akka-apps-redis-channel` Redis
   channel, which the recorder subscribes to. (This requires the plugin's
   `manifest.json` to carry `"eventPersistence": { "isEnabled": true }` —
   shipped in `bbb-plugin-remote-desktop` ≥ 0.3.0-16. Because manifests are
   fetched at meeting-create, a **fresh meeting** is needed to pick it up.)

When either gate drops, the meeting's recorders (and its screenshare index)
stop. When both come back, they restart.

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
| `<unix_user>.fbsx`      | raw-RFB recording of that user's desktop (see below) |
| `<unix_user>.fbsx.json` | sidecar: identity + format metadata |
| `screenshare.jsonl`     | grid-mode projection index (see below) |

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
`meeting_id`, `rfbport`.

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
fbsx-decode /var/lib/bbb-vnc-recorder/<meeting>/<user>.fbsx --ppm /tmp/frame.ppm
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

- `tests/test_gates.py` — gate-2 message classification + screenshare diffing
  (no broker needed).
- `tests/test_fbsx_roundtrip.py` — records a throwaway Xtigervnc desktop with
  Tight *and* Raw, decodes both, asserts the frames are byte-identical and
  Tight is materially smaller (auto-skips if Xtigervnc is absent).

See `~/project/reports/bbb-vnc-recorder.md` for the validation write-up
(what was proven locally vs. what still needs a live grid-mode BBB).

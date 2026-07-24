"""fbsx - raw-RFB "tee" recorder producing the FBSX container.

A DesktopRecorder connects to a live Xtigervnc desktop (shared mode, no
password), performs the RFB 3.8 handshake, negotiates a compact encoding
(Tight by default) and a fixed 32bpp pixel format, then tees every
server->client byte to disk with an epoch-ms timestamp.  It decodes
NOTHING at capture time -- it merely drives incremental
FramebufferUpdateRequests on a timer and records whatever bytes the server
sends.  This keeps the recorder encoding-agnostic and cheap; the stored
FBSX stream is a self-contained, replayable source of truth (see
fbsx-decode.py).

Container FBSX0001:

    magic:  b"FBSX0001\\n"                       (9 bytes)
    record: u32be length, u64be epoch_ms, <length raw server->client bytes>

The stream is teed from the very first byte (the RFB ProtocolVersion), so
a decoder can replay the entire session -- handshake included -- straight
out of the file.  A JSON sidecar <file>.json carries the identity and
format metadata.

Author: Brent Baccala <cosine@freesoft.org>
License: GNU Lesser General Public License
"""

import json
import os
import select
import socket
import struct
import threading
import time

# RFB encoding numbers we advertise (order = server preference).  We ask for
# Tight (compact) first, then CopyRect and Raw as fallbacks, plus the
# DesktopSize and LastRect pseudo-encodings.  We deliberately do NOT request
# the Cursor pseudo-encoding, so the cursor stays baked into the framebuffer.
ENC_RAW = 0
ENC_COPYRECT = 1
ENC_TIGHT = 7
ENC_ZRLE = 16
PSEUDO_DESKTOPSIZE = -223
PSEUDO_LASTRECT = -224

ENCODING_SETS = {
    # name -> list of s32 encoding numbers, most-preferred first
    "tight": [ENC_TIGHT, ENC_COPYRECT, ENC_RAW, PSEUDO_DESKTOPSIZE, PSEUDO_LASTRECT],
    "zrle": [ENC_ZRLE, ENC_COPYRECT, ENC_RAW, PSEUDO_DESKTOPSIZE, PSEUDO_LASTRECT],
    "raw": [ENC_RAW, ENC_COPYRECT, PSEUDO_DESKTOPSIZE, PSEUDO_LASTRECT],
}

# The pixel format we request.  Matches what noVNC asks for (little-endian,
# 32bpp/depth-24 truecolor, red-shift 0 / green-shift 8 / blue-shift 16), so a
# Raw pixel is [R, G, B, pad] and a Tight TPIXEL is [R, G, B].  fbsx-decode.py
# assumes exactly this layout.
PIXEL_FORMAT_NAME = "rgb0"


def now_ms():
    return int(time.time() * 1000)


def _set_pixel_format_msg():
    # SetPixelFormat (msg-type 0) + 3 pad + 16-byte PIXEL_FORMAT
    # bpp=32, depth=24, big-endian=0, true-colour=1,
    # r/g/b-max=255, r-shift=0, g-shift=8, b-shift=16, 3 pad
    pf = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 0, 8, 16)
    return struct.pack(">Bxxx", 0) + pf


def _set_encodings_msg(encodings):
    # SetEncodings (msg-type 2) + 1 pad + u16 count + count * s32
    body = struct.pack(">BxH", 2, len(encodings))
    body += b"".join(struct.pack(">i", e) for e in encodings)
    return body


def _fbur_msg(incremental, x, y, w, h):
    # FramebufferUpdateRequest (msg-type 3)
    return struct.pack(">BBHHHH", 3, 1 if incremental else 0, x, y, w, h)


class DesktopRecorder(threading.Thread):
    """Record one Xtigervnc desktop to an FBSX file until stopped.

    address may be a filesystem path (AF_UNIX, e.g. /run/vnc/<user>) or a
    (host, port) tuple (AF_INET).

    out_path is created exclusively (O_EXCL): an existing recording is NEVER
    truncated.  A collision is reported through .error/.reason like any other
    startup failure, leaving the caller to pick a fresh name -- losing the tail
    of one segment beats overwriting a completed one.
    """

    def __init__(self, address, out_path, identity=None, encoding="tight",
                 fps=10.0, connect_timeout=5.0, on_exit=None, logger=None):
        super().__init__(daemon=True, name="rec-" + os.path.basename(out_path))
        self.address = address
        self.out_path = out_path
        self.identity = dict(identity or {})
        self.encoding = encoding if encoding in ENCODING_SETS else "tight"
        self.fps = max(0.5, float(fps))
        self.connect_timeout = connect_timeout
        self.on_exit = on_exit
        self.log = logger or (lambda *a: None)
        self._stopev = threading.Event()
        self._f = None
        self._sock = None
        self.error = None
        self.geometry = None
        self.desktop_name = None
        self.bytes_written = 0
        self.start_epoch = None
        self.meta = None
        self.reason = None

    # ---- teeing primitives -------------------------------------------------

    def _emit(self, data, ep):
        self._f.write(struct.pack(">IQ", len(data), ep))
        self._f.write(data)
        self.bytes_written += len(data)

    def _recvall(self, n):
        """Receive exactly n bytes, teeing every chunk with a timestamp."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise EOFError("connection closed during handshake")
            self._emit(chunk, now_ms())
            buf += chunk
        return bytes(buf)

    # ---- handshake ---------------------------------------------------------

    def _handshake(self):
        s = self._sock
        ver = self._recvall(12)                       # ProtocolVersion
        rfb_version = ver.decode("latin1", "replace").strip()
        # Reply 3.8 (tigervnc SecurityTypes None speaks 3.8/3.7 identically here)
        s.sendall(b"RFB 003.008\n")
        nsec = self._recvall(1)[0]
        if nsec == 0:
            # server-side failure: u32 reason length + reason
            rlen = struct.unpack(">I", self._recvall(4))[0]
            reason = self._recvall(rlen).decode("latin1", "replace")
            raise RuntimeError("server rejected connection: " + reason)
        self._recvall(nsec)                            # security-types list
        s.sendall(bytes([1]))                          # choose None (type 1)
        self._recvall(4)                               # SecurityResult (u32, 0=OK)
        s.sendall(bytes([1]))                          # ClientInit, shared=1
        hdr = self._recvall(24)                        # ServerInit
        w, h = struct.unpack(">HH", hdr[0:4])
        name_len = struct.unpack(">I", hdr[20:24])[0]
        name = self._recvall(name_len).decode("latin1", "replace")
        self.geometry = (w, h)
        self.desktop_name = name
        # Configure the session.
        s.sendall(_set_pixel_format_msg())
        s.sendall(_set_encodings_msg(ENCODING_SETS[self.encoding]))
        return rfb_version, w, h, name

    def _write_sidecar(self, start_epoch, rfb_version, w, h, name):
        meta = {
            "format": "FBSX0001",
            "start_epoch_ms": start_epoch,
            "geometry": "%dx%d" % (w, h),
            "pixel_format": PIXEL_FORMAT_NAME,
            "encoding": self.encoding,
            "rfb_version": rfb_version,
            "desktop_name": name,
        }
        meta.update(self.identity)
        self.meta = meta
        self._flush_sidecar()

    def _flush_sidecar(self):
        """Write the sidecar atomically (temp file + rename).

        Rewriting in place truncates first, so a process killed between the
        truncate and the flush leaves a 0-byte sidecar -- exactly what an
        upgrade mid-recording produced in the field.  os.replace() is atomic
        within the directory, so a reader sees either the previous complete
        sidecar or the new one, never a partial."""
        if self.meta is None:
            return
        path = self.out_path + ".json"
        tmp = path + ".tmp"
        with open(tmp, "w") as jf:
            json.dump(self.meta, jf, indent=2)
            jf.flush()
            os.fsync(jf.fileno())
        os.replace(tmp, path)

    def _finalize_sidecar(self, end_epoch, reason):
        """Stamp the end of the recording into the sidecar (any exit path).

        Adds end_epoch_ms, duration_ms, bytes_recorded and exit_reason to the
        already-written start metadata and rewrites it.  Best-effort: if the
        handshake never completed there is no sidecar to update."""
        if self.meta is None:
            return
        self.meta["end_epoch_ms"] = end_epoch
        if self.start_epoch is not None:
            self.meta["duration_ms"] = end_epoch - self.start_epoch
        self.meta["bytes_recorded"] = self.bytes_written
        self.meta["exit_reason"] = reason
        try:
            self._flush_sidecar()
        except Exception as e:  # noqa: BLE001
            self.log("failed to finalize sidecar for %s: %r"
                     % (self.out_path, e))

    # ---- main loop ---------------------------------------------------------

    def _connect(self):
        if isinstance(self.address, (tuple, list)):
            self._sock = socket.create_connection(
                tuple(self.address), timeout=self.connect_timeout)
        else:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.connect_timeout)
            s.connect(self.address)
            self._sock = s
        self._sock.settimeout(None)

    def run(self):
        try:
            self._connect()
            self._f = open(self.out_path, "xb")
            self._f.write(b"FBSX0001\n")
            self.start_epoch = now_ms()
            rfb_version, w, h, name = self._handshake()
            self._write_sidecar(self.start_epoch, rfb_version, w, h, name)
            self.log("recording %s -> %s (%dx%d, %s)" %
                     (self.address, self.out_path, w, h, self.encoding))
            # Kick off with a full-screen (non-incremental) request, then drive
            # incremental requests on a timer.  We never parse the replies.
            self._sock.sendall(_fbur_msg(False, 0, 0, w, h))
            interval = 1.0 / self.fps
            next_req = time.monotonic() + interval
            while not self._stopev.is_set():
                timeout = max(0.0, next_req - time.monotonic())
                r, _, _ = select.select([self._sock], [], [], timeout)
                if r:
                    data = self._sock.recv(1 << 16)
                    if not data:
                        if self._stopev.is_set():
                            self.reason = "stopped"
                            self.log("desktop %s: clean stop (socket shut down)"
                                     % (self.address,))
                        else:
                            self.reason = "eof: desktop closed the connection"
                            self.log("desktop %s closed the connection"
                                     % (self.address,))
                        break
                    self._emit(data, now_ms())
                if time.monotonic() >= next_req:
                    try:
                        self._sock.sendall(_fbur_msg(True, 0, 0, w, h))
                    except OSError as e:
                        # Send-side break was previously silent; surface it so a
                        # mid-session connection drop is diagnosable.
                        if self._stopev.is_set():
                            self.reason = "stopped"
                            self.log("desktop %s: clean stop (send interrupted)"
                                     % (self.address,))
                        else:
                            self.reason = "send-failed: %r" % e
                            self.log("desktop %s send failed (FBUR), stopping: %r"
                                     % (self.address, e))
                        break
                    next_req = time.monotonic() + interval
                    self._f.flush()
            else:
                # loop exited because _stopev was set (clean stop)
                self.reason = "stopped"
                self.log("desktop %s: clean stop requested" % (self.address,))
        except Exception as e:  # noqa: BLE001 - record and surface via .error
            self.error = e
            self.reason = "error: %r" % e
            self.log("recorder error on %s: %r" % (self.address, e))
        finally:
            end_epoch = now_ms()
            if self.reason is None:
                self.reason = "unknown"
            try:
                if self._f:
                    self._f.flush()
                    self._f.close()
            except Exception:
                pass
            try:
                if self._sock:
                    self._sock.close()
            except Exception:
                pass
            self._finalize_sidecar(end_epoch, self.reason)
            if self.start_epoch is not None:
                dur = (end_epoch - self.start_epoch) / 1000.0
            else:
                dur = 0.0
            self.log("finished recording %s -> %s (%.1fs, %dB, reason=%s)" %
                     (self.identity.get("unix_user", self.address),
                      self.out_path, dur, self.bytes_written, self.reason))
            if self.on_exit:
                try:
                    self.on_exit(self)
                except Exception:
                    pass

    def stop(self):
        self._stopev.set()
        # nudge select() awake by shutting the socket down for reads
        try:
            if self._sock:
                self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

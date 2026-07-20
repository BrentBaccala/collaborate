#!/usr/bin/env python3
"""fbsx-decode - replay an FBSX recording and prove it is a source of truth.

Reconstructs the raw server->client RFB stream stored in an FBSX file,
replays the handshake, decodes framebuffer updates, associates each update
with its epoch-ms timestamp, and writes the final framebuffer as a PPM
(proof the stored bytes reproduce the desktop pixels).  Supports the
encodings this recorder negotiates: Raw(0), CopyRect(1), Tight(7), plus the
DesktopSize(-223) and LastRect(-224) pseudo-encodings.

The Tight decoder is a faithful Python port of noVNC's decoders/tight.js,
matching the 32bpp/depth-24 pixel format the recorder requests (TPIXEL =
[R, G, B]).

    usage: fbsx-decode.py FILE.fbsx [--ppm OUT.ppm]

Prints an analysis JSON to stdout.

Author: Brent Baccala <cosine@freesoft.org>
License: GNU Lesser General Public License
"""

import argparse
import json
import struct
import sys
import zlib


# --------------------------------------------------------------------------
# Timed reader over the FBSX record list: yields the reconstructed RFB byte
# stream while tracking the epoch-ms of the record each byte came from.
# --------------------------------------------------------------------------
class TimedReader:
    def __init__(self, records):
        self.records = records
        self.i = 0
        self.off = 0
        self.cur_epoch = None

    def read(self, n):
        out = bytearray()
        while len(out) < n:
            if self.i >= len(self.records):
                raise EOFError
            ep, data = self.records[self.i]
            self.cur_epoch = ep
            take = data[self.off:self.off + (n - len(out))]
            out += take
            self.off += len(take)
            if self.off >= len(data):
                self.i += 1
                self.off = 0
        return bytes(out)

    def u8(self):
        return self.read(1)[0]

    def u16(self):
        return struct.unpack(">H", self.read(2))[0]

    def u32(self):
        return struct.unpack(">I", self.read(4))[0]

    def s32(self):
        return struct.unpack(">i", self.read(4))[0]


# --------------------------------------------------------------------------
# Framebuffer: RGB (3 bytes/pixel), row-major.
# --------------------------------------------------------------------------
class Framebuffer:
    def __init__(self, w, h):
        self.resize(w, h)

    def resize(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    def blit_rgb(self, x, y, w, h, rgb):
        """rgb is w*h*3 bytes, row-major."""
        for row in range(h):
            dst = ((y + row) * self.w + x) * 3
            src = row * w * 3
            self.buf[dst:dst + w * 3] = rgb[src:src + w * 3]

    def fill(self, x, y, w, h, r, g, b):
        px = bytes((r, g, b))
        for row in range(h):
            base = ((y + row) * self.w + x) * 3
            for col in range(w):
                o = base + col * 3
                self.buf[o:o + 3] = px

    def copyrect(self, x, y, w, h, sx, sy):
        # copy source region (may overlap); snapshot rows first
        rows = []
        for row in range(h):
            so = ((sy + row) * self.w + sx) * 3
            rows.append(bytes(self.buf[so:so + w * 3]))
        for row in range(h):
            do = ((y + row) * self.w + x) * 3
            self.buf[do:do + w * 3] = rows[row]

    def write_ppm(self, path):
        with open(path, "wb") as f:
            f.write(b"P6\n%d %d\n255\n" % (self.w, self.h))
            f.write(bytes(self.buf))


# --------------------------------------------------------------------------
# Tight decoder -- faithful port of noVNC decoders/tight.js.  Assumes 3-byte
# TPIXEL in [R, G, B] order (the recorder's requested pixel format).
# --------------------------------------------------------------------------
class TightDecoder:
    def __init__(self):
        self._zlibs = [None, None, None, None]  # lazily-created decompressobj

    def _reset_stream(self, i):
        self._zlibs[i] = zlib.decompressobj()

    def _inflate(self, stream_id, data, expected):
        if self._zlibs[stream_id] is None:
            self._zlibs[stream_id] = zlib.decompressobj()
        out = self._zlibs[stream_id].decompress(data, expected)
        # A Tight rectangle's compressed chunk is Z_SYNC_FLUSH-terminated, so a
        # single decompress() call yields exactly `expected` bytes.
        while len(out) < expected:
            more = self._zlibs[stream_id].decompress(b"", expected - len(out))
            if not more:
                break
            out += more
        return out

    @staticmethod
    def _read_compact_len(r):
        b = r.u8()
        length = b & 0x7f
        if b & 0x80:
            b = r.u8()
            length |= (b & 0x7f) << 7
            if b & 0x80:
                b = r.u8()
                length |= b << 14
        return length

    def decode_rect(self, r, fb, x, y, w, h):
        ctl = r.u8()
        for i in range(4):
            if (ctl >> i) & 1:
                self._reset_stream(i)
        ctl >>= 4
        if ctl == 0x08:                       # fill
            r_, g_, b_ = r.read(3)
            fb.fill(x, y, w, h, r_, g_, b_)
        elif ctl == 0x09:                     # jpeg
            data = r.read(self._read_compact_len(r))
            self._blit_jpeg(fb, x, y, w, h, data)
        elif (ctl & 0x08) == 0:               # basic compression
            self._basic(ctl, r, fb, x, y, w, h)
        else:
            raise ValueError("illegal Tight compression ctl=0x%x" % ctl)

    def _basic(self, ctl, r, fb, x, y, w, h):
        if ctl & 0x4:
            filt = r.u8()
        else:
            filt = 0                           # implicit CopyFilter
        stream_id = ctl & 0x3
        if filt == 0:
            self._copy_filter(stream_id, r, fb, x, y, w, h)
        elif filt == 1:
            self._palette_filter(stream_id, r, fb, x, y, w, h)
        elif filt == 2:
            self._gradient_filter(stream_id, r, fb, x, y, w, h)
        else:
            raise ValueError("illegal Tight filter %d" % filt)

    def _read_pixels(self, stream_id, r, uncompressed):
        if uncompressed == 0:
            return b""
        if uncompressed < 12:
            return r.read(uncompressed)
        comp = r.read(self._read_compact_len(r))
        return self._inflate(stream_id, comp, uncompressed)

    def _copy_filter(self, stream_id, r, fb, x, y, w, h):
        data = self._read_pixels(stream_id, r, w * h * 3)
        fb.blit_rgb(x, y, w, h, data)          # already RGB

    def _palette_filter(self, stream_id, r, fb, x, y, w, h):
        num_colors = r.u8() + 1
        palette = r.read(num_colors * 3)       # RGB entries
        bpp = 1 if num_colors <= 2 else 8
        row_size = (w * bpp + 7) // 8
        data = self._read_pixels(stream_id, r, row_size * h)
        rgb = bytearray(w * h * 3)
        if num_colors == 2:
            for yy in range(h):
                for xx in range(w):
                    byte = data[yy * row_size + (xx >> 3)]
                    idx = (byte >> (7 - (xx & 7))) & 1
                    o = (yy * w + xx) * 3
                    s = idx * 3
                    rgb[o:o + 3] = palette[s:s + 3]
        else:
            for i in range(w * h):
                s = data[i] * 3
                rgb[i * 3:i * 3 + 3] = palette[s:s + 3]
        fb.blit_rgb(x, y, w, h, rgb)

    def _gradient_filter(self, stream_id, r, fb, x, y, w, h):
        data = self._read_pixels(stream_id, r, w * h * 3)
        rgb = bytearray(w * h * 3)
        prev_row = [0] * (w * 3)
        for yy in range(h):
            left = [0, 0, 0]
            upperleft = [0, 0, 0]
            for xx in range(w):
                for c in range(3):
                    up = prev_row[xx * 3 + c] if yy > 0 else 0
                    if yy == 0:
                        pred = left[c]
                    else:
                        pred = left[c] + up - upperleft[c]
                        pred = 0 if pred < 0 else (255 if pred > 255 else pred)
                    val = (data[(yy * w + xx) * 3 + c] + pred) & 0xff
                    rgb[(yy * w + xx) * 3 + c] = val
                    if yy > 0:
                        upperleft[c] = up
                    left[c] = val
            prev_row = list(rgb[yy * w * 3:(yy + 1) * w * 3])
        fb.blit_rgb(x, y, w, h, rgb)

    @staticmethod
    def _blit_jpeg(fb, x, y, w, h, data):
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data)).convert("RGB")
            fb.blit_rgb(x, y, w, h, im.tobytes())
        except ImportError:
            # No PIL: leave region as-is but don't fail the whole decode.
            sys.stderr.write("warning: JPEG rect skipped (PIL not installed)\n")


def load_records(path):
    records = []
    with open(path, "rb") as fh:
        magic = fh.read(9)
        if magic != b"FBSX0001\n":
            raise ValueError("not an FBSX0001 file (magic=%r)" % magic)
        while True:
            head = fh.read(12)
            if len(head) < 12:
                break
            ln, ep = struct.unpack(">IQ", head)
            records.append((ep, fh.read(ln)))
    return records


def decode(path, ppm_out=None):
    records = load_records(path)
    r = TimedReader(records)
    # Replay handshake exactly as the recorder wrote it.
    r.read(12)                                 # ProtocolVersion
    nsec = r.u8()
    r.read(nsec)                               # security-types
    r.read(4)                                  # SecurityResult
    hdr = r.read(24)                           # ServerInit
    w, h = struct.unpack(">HH", hdr[0:4])
    name_len = struct.unpack(">I", hdr[20:24])[0]
    r.read(name_len)
    fb = Framebuffer(w, h)
    tight = TightDecoder()
    events = []                                # (epoch_ms, n_rects, byte_span)

    def read_message():
        t = r.u8()
        if t == 0:                             # FramebufferUpdate
            r.read(1)
            n = r.u16()
            start_idx = r.i
            count = 0
            while True:
                if n != 0xffff and count >= n:
                    break
                x = r.u16(); y = r.u16(); rw = r.u16(); rh = r.u16()
                enc = r.s32()
                if enc == -224:                # LastRect
                    break
                elif enc == -223:              # DesktopSize
                    fb.resize(rw, rh)
                elif enc == 0:                 # Raw (4 bytes/pixel: R,G,B,pad)
                    px = r.read(rw * rh * 4)
                    rgb = bytearray(rw * rh * 3)
                    for i in range(rw * rh):
                        rgb[i * 3:i * 3 + 3] = px[i * 4:i * 4 + 3]
                    fb.blit_rgb(x, y, rw, rh, rgb)
                elif enc == 1:                 # CopyRect
                    sx = r.u16(); sy = r.u16()
                    fb.copyrect(x, y, rw, rh, sx, sy)
                elif enc == 7:                 # Tight
                    tight.decode_rect(r, fb, x, y, rw, rh)
                else:
                    raise ValueError("unsupported encoding %d" % enc)
                count += 1
            events.append((r.cur_epoch, count, r.i - start_idx))
        elif t == 1:                           # SetColourMapEntries
            r.read(3); nc = r.u16(); r.read(nc * 6)
        elif t == 2:                           # Bell
            pass
        elif t == 3:                           # ServerCutText
            r.read(3); ln = r.u32(); r.read(ln)
        else:
            raise ValueError("unknown server message type %d" % t)

    try:
        while True:
            read_message()
    except EOFError:
        pass

    if ppm_out:
        fb.write_ppm(ppm_out)
    return {
        "file": path,
        "geometry": "%dx%d" % (fb.w, fb.h),
        "n_records": len(records),
        "bytes_on_disk": sum(len(d) for _, d in records),
        "n_updates": len(events),
        "update_epochs": [e[0] for e in events],
        "ppm": ppm_out,
    }


def main():
    ap = argparse.ArgumentParser(description="Decode/verify an FBSX recording.")
    ap.add_argument("file")
    ap.add_argument("--ppm", help="write final framebuffer as PPM")
    args = ap.parse_args()
    default_ppm = args.ppm or (args.file + ".ppm")
    print(json.dumps(decode(args.file, default_ppm), indent=2))


if __name__ == "__main__":
    main()

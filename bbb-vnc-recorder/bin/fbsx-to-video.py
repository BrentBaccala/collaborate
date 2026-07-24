#!/usr/bin/env python3
"""fbsx-to-video -- transcode an FBSX recording into a real-time playback video.

The recorder is capture-only; this is the companion decode/playback tool. It
reuses the Tight/Raw decoder from ``fbsx-decode`` (installed alongside), snapshots
the framebuffer after every update, and rebuilds a video whose frame timing
follows the recording's epoch-ms timestamps (variable-rate source resampled to a
constant-rate H.264 mp4, or VP9 webm if the output ends in .webm).

    usage: fbsx-to-video FILE.fbsx [OUT] [--fps N]

OUT defaults to <FILE>.mp4.  Needs ffmpeg on PATH; Tight-JPEG regions also need
python3-pil (missing PIL just skips those rects, same as fbsx-decode).
"""
import argparse
import importlib.util
import os
import struct
import subprocess
import sys
from importlib.machinery import SourceFileLoader


def _load_decoder():
    """Load the sibling fbsx-decode module (installed as 'fbsx-decode', in-repo
    as 'fbsx-decode.py') regardless of its extension."""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("fbsx-decode", "fbsx-decode.py"):
        path = os.path.join(here, name)
        if os.path.exists(path):
            loader = SourceFileLoader("fbsx_decode", path)
            spec = importlib.util.spec_from_loader("fbsx_decode", loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            return mod
    sys.exit("fbsx-to-video: cannot find fbsx-decode next to this script")


def transcode(fbsx, out, fps=10):
    m = _load_decoder()
    r = m.TimedReader(m.load_records(fbsx))
    r.read(12); nsec = r.u8(); r.read(nsec); r.read(4)      # handshake
    hdr = r.read(24)
    w, h = struct.unpack(">HH", hdr[0:4])
    r.read(struct.unpack(">I", hdr[20:24])[0])              # desktop name
    fb = m.Framebuffer(w, h)
    tight = m.TightDecoder()

    # Frames stream straight into ffmpeg; nothing is staged to disk.  The
    # source is variable-rate (one snapshot per FramebufferUpdate), so the
    # VFR -> CFR resample the old concat-list + `-r` did happens here instead:
    # walk the recording clock in 1000/fps ticks, holding each snapshot for its
    # real inter-update duration.  Staging every frame as an uncompressed
    # w*h*3 PPM first was tens of GB for a long busy desktop and filled the
    # disk mid-run; peak temp-disk is now 0 and peak RAM one framebuffer copy,
    # with pipe backpressure throttling the decoder to ffmpeg's encode rate.
    W, H = w, h                                             # fixed pipe geometry
    period = 1000.0 / fps                                   # output tick, ms

    if out.endswith(".webm"):
        vcodec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32"]
    else:
        vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                  "-movflags", "+faststart"]
    ff = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pixel_format", "rgb24",
         "-video_size", "%dx%d" % (W, H), "-framerate", str(fps), "-i", "-",
         "-r", str(fps), "-pix_fmt", "yuv420p"] + vcodec + ["-y", out],
        stdin=subprocess.PIPE)

    snaps = 0
    first = last = pend = None
    outclk = 0.0

    def conform():
        """Current framebuffer as W*H*3 rgb24.  rawvideo over a pipe needs a
        fixed frame size, so a mid-stream DesktopSize is padded/cropped to the
        initial geometry (the old concat-of-PPMs path failed outright on it)."""
        if fb.w == W and fb.h == H:
            return bytes(fb.buf)
        buf = bytearray(W * H * 3)
        cols = min(fb.w, W) * 3
        for row in range(min(fb.h, H)):
            buf[row * W * 3:row * W * 3 + cols] = \
                fb.buf[row * fb.w * 3:row * fb.w * 3 + cols]
        return bytes(buf)

    def emit(frame):
        """Write one output frame, turning a dead ffmpeg into a clean error."""
        try:
            ff.stdin.write(frame)
        except BrokenPipeError:
            ff.wait()
            sys.exit("fbsx-to-video: ffmpeg exited %d mid-stream" % ff.returncode)

    try:
        def snap(epoch):
            nonlocal snaps, first, last, pend, outclk
            snaps += 1
            cur = conform()
            if pend is None:
                first = epoch
                outclk = float(epoch)
            else:
                while outclk < epoch:               # hold prev frame until now
                    emit(pend)
                    outclk += period
            pend = cur
            last = epoch

        def read_message():
            t = r.u8()
            if t == 0:                                     # FramebufferUpdate
                r.read(1); n = r.u16(); count = 0
                while not (n != 0xffff and count >= n):
                    x = r.u16(); y = r.u16(); rw = r.u16(); rh = r.u16(); enc = r.s32()
                    if enc == -224:                        # LastRect
                        break
                    elif enc == -223:                      # DesktopSize
                        fb.resize(rw, rh)
                    elif enc == 0:                         # Raw
                        px = r.read(rw * rh * 4)
                        rgb = bytearray(rw * rh * 3)
                        for i in range(rw * rh):
                            rgb[i * 3:i * 3 + 3] = px[i * 4:i * 4 + 3]
                        fb.blit_rgb(x, y, rw, rh, rgb)
                    elif enc == 1:                         # CopyRect
                        sx = r.u16(); sy = r.u16()
                        fb.copyrect(x, y, rw, rh, sx, sy)
                    elif enc == 7:                         # Tight
                        tight.decode_rect(r, fb, x, y, rw, rh)
                    else:
                        raise ValueError("unsupported encoding %d" % enc)
                    count += 1
                snap(r.cur_epoch)
            elif t == 1:                                   # SetColourMapEntries
                r.read(3); nc = r.u16(); r.read(nc * 6)
            elif t == 2:                                   # Bell
                pass
            elif t == 3:                                   # ServerCutText
                r.read(3); ln = r.u32(); r.read(ln)
            else:
                raise ValueError("unknown server message type %d" % t)

        try:
            while True:
                read_message()
        except EOFError:
            pass

        if pend is None:
            ff.stdin.close()
            ff.wait()
            sys.exit("fbsx-to-video: no framebuffer updates decoded")

        end = last + 3000                                   # hold final frame 3s
        while outclk < end:
            emit(pend)
            outclk += period
        ff.stdin.close()
    finally:
        try:
            if ff.stdin and not ff.stdin.closed:
                ff.stdin.close()
        except BrokenPipeError:
            pass
        ff.wait()

    if ff.returncode:
        sys.exit("fbsx-to-video: ffmpeg exited %d" % ff.returncode)
    return snaps, (last - first) / 1000.0


def main():
    ap = argparse.ArgumentParser(description="Transcode an FBSX recording to a real-time video.")
    ap.add_argument("file")
    ap.add_argument("out", nargs="?", help="output video (default: <file>.mp4; .webm also supported)")
    ap.add_argument("--fps", type=int, default=10, help="output constant frame rate (default 10)")
    args = ap.parse_args()
    out = args.out or (os.path.splitext(args.file)[0] + ".mp4")
    n, span = transcode(args.file, out, args.fps)
    print("wrote %s (%d frames, %.1fs)" % (out, n, span))


if __name__ == "__main__":
    main()

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
import shutil
import struct
import subprocess
import sys
import tempfile
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
    frames = []
    tmp = tempfile.mkdtemp(prefix="fbsx-frames-")
    try:
        def snap(epoch):
            p = os.path.join(tmp, "f%06d.ppm" % len(frames))
            fb.write_ppm(p)
            frames.append((epoch, p))

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

        if not frames:
            sys.exit("fbsx-to-video: no framebuffer updates decoded")

        # concat list with each frame held for its real inter-update duration
        listpath = os.path.join(tmp, "list.txt")
        with open(listpath, "w") as lst:
            for i, (epoch, path) in enumerate(frames):
                dur = (frames[i + 1][0] - epoch) / 1000.0 if i + 1 < len(frames) else 3.0
                lst.write("file '%s'\nduration %.3f\n" % (path, max(dur, 0.001)))
            lst.write("file '%s'\n" % frames[-1][1])       # concat quirk: repeat last

        if out.endswith(".webm"):
            vcodec = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32"]
        else:
            vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                      "-movflags", "+faststart"]
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", listpath,
                        "-r", str(fps), "-pix_fmt", "yuv420p"] + vcodec + ["-y", out],
                       check=True)
        return len(frames), (frames[-1][0] - frames[0][0]) / 1000.0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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

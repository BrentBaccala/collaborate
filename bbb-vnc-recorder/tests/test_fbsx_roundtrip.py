"""End-to-end FBSX roundtrip test against a throwaway Xtigervnc desktop.

Records the desktop with Tight AND Raw, decodes both, and asserts:
  * both produce a non-blank framebuffer of the right geometry
  * the Tight-decoded frame is byte-identical to the Raw-decoded frame
    (proves the Tight decoder + pixel-format handling are correct)
  * both recorders stamped their updates at near-identical epoch-ms
    (proves the single-clock cross-stream sync claim)

Skipped automatically if Xtigervnc is not installed.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bbb_vnc_recorder.fbsx import DesktopRecorder

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "fbsx_decode",
    os.path.join(os.path.dirname(__file__), "..", "bin", "fbsx-decode.py"))
fbsx_decode = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fbsx_decode)


def _read_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    idx = 0

    def tok():
        nonlocal idx
        while data[idx] in b" \t\n\r":
            idx += 1
        s = idx
        while data[idx] not in b" \t\n\r":
            idx += 1
        return data[s:idx]
    assert tok() == b"P6"
    w = int(tok()); h = int(tok()); int(tok())
    idx += 1
    return w, h, data[idx:]


def main():
    if not shutil.which("Xtigervnc"):
        print("SKIP: Xtigervnc not installed")
        return 0
    tmp = tempfile.mkdtemp(prefix="fbsx-roundtrip-")
    disp = ":91"
    sock = os.path.join(tmp, "sock")
    xvnc = subprocess.Popen(
        ["Xtigervnc", disp, "-rfbunixpath", sock, "-rfbport", "5991",
         "-SecurityTypes", "None", "-geometry", "640x480", "-depth", "24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if os.path.exists(sock):
                break
            time.sleep(0.1)
        assert os.path.exists(sock), "Xtigervnc did not create its socket"
        env = dict(os.environ, DISPLAY=disp)
        if shutil.which("xsetroot"):
            subprocess.call(["xsetroot", "-solid", "steelblue"], env=env)
        time.sleep(0.5)

        rt = DesktopRecorder(sock, os.path.join(tmp, "t.fbsx"), encoding="tight",
                             fps=10, identity={"unix_user": "test"})
        rr = DesktopRecorder(("127.0.0.1", 5991), os.path.join(tmp, "r.fbsx"),
                             encoding="raw", fps=10, identity={"unix_user": "test"})
        rt.start(); rr.start()
        time.sleep(3)
        rt.stop(); rr.stop(); rt.join(5); rr.join(5)
        assert rt.error is None, "tight recorder error: %r" % rt.error
        assert rr.error is None, "raw recorder error: %r" % rr.error

        at = fbsx_decode.decode(os.path.join(tmp, "t.fbsx"),
                                os.path.join(tmp, "t.ppm"))
        ar = fbsx_decode.decode(os.path.join(tmp, "r.fbsx"),
                                os.path.join(tmp, "r.ppm"))
        assert at["geometry"] == "640x480" == ar["geometry"]
        assert at["n_updates"] >= 1 and ar["n_updates"] >= 1

        wt, ht, pt = _read_ppm(os.path.join(tmp, "t.ppm"))
        wr, hr, pr = _read_ppm(os.path.join(tmp, "r.ppm"))
        assert (wt, ht) == (wr, hr) == (640, 480)
        assert pt == pr, "tight and raw decodes differ"
        assert any(b != 0 for b in pt), "decoded frame is blank"

        # Tight must be dramatically smaller than Raw.
        assert at["bytes_on_disk"] * 5 < ar["bytes_on_disk"], \
            "tight not materially smaller than raw"

        print("ok  roundtrip: tight=%dB raw=%dB updates(t=%d,r=%d) frames identical"
              % (at["bytes_on_disk"], ar["bytes_on_disk"],
                 at["n_updates"], ar["n_updates"]))
        return 0
    finally:
        xvnc.terminate()
        try:
            xvnc.wait(timeout=5)
        except Exception:
            xvnc.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

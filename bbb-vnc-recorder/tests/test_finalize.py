"""Finalize / connection-break / restart-no-clobber tests for the recorder.

Covers the gate-1-fix follow-up requirements:
  * every DesktopRecorder exit path writes end_epoch_ms + duration + reason
    into the sidecar and logs a one-line "finished recording ..." summary;
  * a clean stop is reasoned "stopped"; a server that vanishes mid-recording
    is reasoned "eof"/"send-failed" (NOT a silent break);
  * a mid-session drop + restart writes a NEW numbered part file
    (<user>.<n>.fbsx) and does not truncate the earlier segment -- both within
    one process and across a process restart (numbering is seeded from the
    meeting directory, and part files are opened O_EXCL).

Skipped automatically if Xtigervnc is not installed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bbb_vnc_recorder.fbsx import DesktopRecorder
from bbb_vnc_recorder.recorder import MeetingSession


def _start_xvnc(sock, disp=":92", port="5992"):
    p = subprocess.Popen(
        ["Xtigervnc", disp, "-rfbunixpath", sock, "-rfbport", port,
         "-SecurityTypes", "None", "-geometry", "640x480", "-depth", "24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if os.path.exists(sock):
            break
        time.sleep(0.1)
    return p


def _kill(p):
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()


def _load_sidecar(path):
    with open(path + ".json") as f:
        return json.load(f)


def test_clean_stop_finalizes():
    tmp = tempfile.mkdtemp(prefix="fbsx-final-")
    sock = os.path.join(tmp, "sock")
    logs = []
    xvnc = _start_xvnc(sock)
    try:
        assert os.path.exists(sock), "Xtigervnc did not create its socket"
        out = os.path.join(tmp, "u.1.fbsx")
        rec = DesktopRecorder(sock, out, encoding="tight", fps=10,
                              identity={"unix_user": "u"},
                              logger=lambda *a: logs.append(" ".join(map(str, a))))
        rec.start()
        time.sleep(1.5)
        rec.stop()
        rec.join(5)
        assert rec.error is None, "unexpected error: %r" % rec.error
        assert rec.reason == "stopped", "reason was %r" % rec.reason
        meta = _load_sidecar(out)
        assert "start_epoch_ms" in meta and "end_epoch_ms" in meta
        assert meta["end_epoch_ms"] >= meta["start_epoch_ms"]
        assert meta["duration_ms"] >= 0
        assert meta["bytes_recorded"] > 0
        assert meta["exit_reason"] == "stopped"
        assert any("finished recording" in l for l in logs), \
            "no finish summary logged: %r" % logs
        print("ok  clean stop finalizes: reason=%s dur=%dms bytes=%d"
              % (meta["exit_reason"], meta["duration_ms"], meta["bytes_recorded"]))
    finally:
        _kill(xvnc)
        shutil.rmtree(tmp, ignore_errors=True)


def test_server_vanish_is_not_silent():
    """A server that dies mid-recording must exit with a logged reason and a
    finalized sidecar (the previously-silent `except OSError: break` path)."""
    tmp = tempfile.mkdtemp(prefix="fbsx-drop-")
    sock = os.path.join(tmp, "sock")
    logs = []
    xvnc = _start_xvnc(sock)
    try:
        assert os.path.exists(sock)
        out = os.path.join(tmp, "u.1.fbsx")
        rec = DesktopRecorder(sock, out, encoding="tight", fps=10,
                              identity={"unix_user": "u"},
                              logger=lambda *a: logs.append(" ".join(map(str, a))))
        rec.start()
        time.sleep(1.0)
        # Yank the server out from under the recorder.
        _kill(xvnc)
        rec.join(8)
        assert not rec.is_alive(), "recorder did not exit after server death"
        assert rec.reason is not None and rec.reason != "unknown", \
            "exit reason not captured: %r" % rec.reason
        assert ("eof" in rec.reason or "send-failed" in rec.reason
                or rec.reason.startswith("error")), "reason=%r" % rec.reason
        meta = _load_sidecar(out)
        assert "end_epoch_ms" in meta
        assert meta["exit_reason"] == rec.reason
        assert any("finished recording" in l for l in logs)
        print("ok  server vanish surfaced: reason=%s" % rec.reason)
    finally:
        _kill(xvnc)
        shutil.rmtree(tmp, ignore_errors=True)


def test_restart_no_clobber_segments():
    """A drop + restart of a desktop's recorder writes a NEW numbered part
    file and leaves the earlier segment intact (never truncates it)."""
    tmp = tempfile.mkdtemp(prefix="fbsx-seg-")
    run_dir = os.path.join(tmp, "run")
    os.makedirs(run_dir)
    sock = os.path.join(run_dir, "u")
    xvnc = _start_xvnc(sock)
    try:
        assert os.path.exists(sock)
        cfg = {
            "storage": {"directory": os.path.join(tmp, "store")},
            "vnc": {"run_dir": run_dir},
            "recording": {"encoding": "tight", "fps": 10},
        }
        sess = MeetingSession("mtg-1", "ext-1", cfg)
        # segment 1
        sess.update(["u"])
        time.sleep(1.2)
        seg1 = os.path.join(sess.directory, "u.1.fbsx")
        assert os.path.exists(seg1), "segment 1 not created"
        # simulate a mid-session drop: stop the live recorder (its on_exit
        # removes it from the session), as a connection break would.
        rec1 = sess.recorders["u"]
        rec1.stop()
        rec1.join(5)
        size1 = os.path.getsize(seg1)
        assert size1 > 0
        # session is KEPT (not torn down), so the segment counter persists.
        assert "u" not in sess.recorders  # dropped via on_exit
        assert sess._segments["u"] == 1
        # restart: must open a NEW part file, not reuse u.1.fbsx.
        sess.update(["u"])
        time.sleep(1.0)
        seg2 = os.path.join(sess.directory, "u.2.fbsx")
        assert os.path.exists(seg2), "segment 2 not created on restart"
        assert sess._segments["u"] == 2
        # the first segment must be untouched (not truncated / reopened).
        assert os.path.getsize(seg1) == size1, "segment 1 was clobbered!"
        m1 = _load_sidecar(seg1)
        assert m1["segment"] == 1 and m1["exit_reason"] == "stopped"
        rec2 = sess.recorders.get("u")
        sess.stop()
        if rec2 is not None:
            rec2.join(5)
        print("ok  restart no-clobber: seg1=%dB preserved, seg2 opened fresh"
              % size1)
    finally:
        _kill(xvnc)
        shutil.rmtree(tmp, ignore_errors=True)


def test_new_process_no_clobber_segments():
    """A NEW recorder process (service restart / crash / apt upgrade) resumes
    numbering from the meeting directory instead of restarting at .1 and
    overwriting the segment a previous process wrote.

    This is the field failure: an upgrade stopped the recorder mid-meeting, the
    restart re-opened <user>.1.fbsx, and a 75-second re-take replaced a 134 MB
    capture."""
    tmp = tempfile.mkdtemp(prefix="fbsx-restart-")
    run_dir = os.path.join(tmp, "run")
    os.makedirs(run_dir)
    sock = os.path.join(run_dir, "u")
    xvnc = _start_xvnc(sock)
    try:
        assert os.path.exists(sock)
        cfg = {
            "storage": {"directory": os.path.join(tmp, "store")},
            "vnc": {"run_dir": run_dir},
            "recording": {"encoding": "tight", "fps": 10},
        }
        # ---- first process: records segment 1, then dies without cleanup
        sess = MeetingSession("mtg-1", "ext-1", cfg)
        sess.update(["u"])
        time.sleep(1.2)
        seg1 = os.path.join(sess.directory, "u.1.fbsx")
        assert os.path.exists(seg1), "segment 1 not created"
        rec1 = sess.recorders["u"]
        rec1.stop()
        rec1.join(5)
        size1 = os.path.getsize(seg1)
        assert size1 > 0
        del sess                        # the process is gone; counter with it

        # ---- second process: same meeting, fresh in-memory state
        sess2 = MeetingSession("mtg-1", "ext-1", cfg)
        assert sess2._segments == {}, "new session started with stale state"
        sess2.update(["u"])
        time.sleep(1.0)
        seg2 = os.path.join(sess2.directory, "u.2.fbsx")
        assert os.path.exists(seg2), \
            "restart did not open a new segment (files: %s)" % \
            sorted(os.listdir(sess2.directory))
        assert os.path.getsize(seg1) == size1, \
            "segment 1 was clobbered by the restart!"
        m1 = _load_sidecar(seg1)
        assert m1["segment"] == 1
        rec2 = sess2.recorders.get("u")
        sess2.stop()
        if rec2 is not None:
            rec2.join(5)
        print("ok  restart across processes: seg1=%dB preserved, seg2 opened fresh"
              % size1)
    finally:
        _kill(xvnc)
        shutil.rmtree(tmp, ignore_errors=True)


def test_recorder_never_truncates_existing_file():
    """Belt and braces: a DesktopRecorder pointed at an existing part file must
    fail rather than truncate it, whatever the caller's numbering did."""
    tmp = tempfile.mkdtemp(prefix="fbsx-excl-")
    sock = os.path.join(tmp, "sock")
    xvnc = _start_xvnc(sock)
    try:
        assert os.path.exists(sock)
        out = os.path.join(tmp, "u.1.fbsx")
        with open(out, "wb") as f:
            f.write(b"PRIOR RECORDING")
        rec = DesktopRecorder(sock, out, encoding="tight", fps=10,
                              identity={"unix_user": "u"})
        rec.start()
        rec.join(5)
        assert not rec.is_alive()
        assert isinstance(rec.error, FileExistsError), \
            "expected FileExistsError, got %r" % rec.error
        with open(out, "rb") as f:
            assert f.read() == b"PRIOR RECORDING", "existing file was truncated!"
        print("ok  exclusive open: existing recording left intact (%r)" % rec.reason)
    finally:
        _kill(xvnc)
        shutil.rmtree(tmp, ignore_errors=True)


def _run():
    if not shutil.which("Xtigervnc"):
        print("SKIP: Xtigervnc not installed")
        return 0, 0
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
    print("\n%d/%d passed" % (passed, len(fns)))
    return passed, len(fns)


if __name__ == "__main__":
    p, n = _run()
    sys.exit(0 if p == n else 1)

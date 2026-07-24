"""Unit tests for gate-2 message classification and screenshare diffing.

Run: python3 -m pytest tests/  (or python3 tests/test_gates.py)
No live Redis / Postgres needed.
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bbb_vnc_recorder.gates import (classify_message,
                                    classify_recording_message,
                                    AkkaEventWatcher, ShareGateWatcher)
from bbb_vnc_recorder.screenshare import diff_snapshots


def _persist_msg(plugin, event, meeting="mtg-internal-1"):
    return {
        "envelope": {"name": "PluginPersistEventEvtMsg",
                     "routing": {"msgType": "BROADCAST_TO_MEETING"}},
        "core": {
            "header": {"name": "PluginPersistEventEvtMsg",
                       "meetingId": meeting, "userId": "u1"},
            "body": {"pluginName": plugin, "eventName": event,
                     "payloadJson": {"url": "wss://x/vnc", "sharedBy": "Teacher"}},
        },
    }


def _recording_msg(recording, meeting="mtg-internal-1", set_by="mod1"):
    # Mirrors BBB 3.0 RecordingStatusChangedEvtMsg
    # (common2 UsersMsgs.scala: body {recording, setBy}).
    return {
        "envelope": {"name": "RecordingStatusChangedEvtMsg",
                     "routing": {"msgType": "BROADCAST_TO_MEETING"}},
        "core": {
            "header": {"name": "RecordingStatusChangedEvtMsg",
                       "meetingId": meeting, "userId": set_by},
            "body": {"recording": recording, "setBy": set_by},
        },
    }


def test_share_start():
    action, mid = classify_message(_persist_msg("RemoteDesktop",
                                                "remote-desktop-share-start"))
    assert action == "share-start"
    assert mid == "mtg-internal-1"


def test_share_stop():
    action, mid = classify_message(_persist_msg("RemoteDesktop",
                                                "remote-desktop-share-stop"))
    assert action == "share-stop"


def test_other_plugin_ignored():
    action, _ = classify_message(_persist_msg("SomeOtherPlugin",
                                              "remote-desktop-share-start"))
    assert action is None


def test_other_event_ignored():
    action, _ = classify_message(_persist_msg("RemoteDesktop", "some-other-event"))
    assert action is None


def test_non_persist_message_ignored():
    msg = {"envelope": {"name": "GetRecordingStatusRespMsg"},
           "core": {"header": {"name": "GetRecordingStatusRespMsg"}, "body": {}}}
    action, _ = classify_message(msg)
    assert action is None


def test_malformed_message_ignored():
    assert classify_message({}) == (None, None)
    assert classify_message({"core": "notadict"}) == (None, None)


def test_watcher_state_and_transitions():
    changes = []
    w = ShareGateWatcher({"channels": ["c"]},
                         {"name": "RemoteDesktop",
                          "share_start_event": "remote-desktop-share-start",
                          "share_stop_event": "remote-desktop-share-stop"},
                         on_change=lambda mid, s: changes.append((mid, s)))
    assert w.is_sharing("m1") is False
    w.handle_raw(json.dumps(_persist_msg("RemoteDesktop",
                                         "remote-desktop-share-start", "m1")))
    assert w.is_sharing("m1") is True
    # duplicate start = no new transition
    w.handle_raw(json.dumps(_persist_msg("RemoteDesktop",
                                         "remote-desktop-share-start", "m1")))
    w.handle_raw(json.dumps(_persist_msg("RemoteDesktop",
                                         "remote-desktop-share-stop", "m1")))
    assert w.is_sharing("m1") is False
    assert changes == [("m1", True), ("m1", False)]


# ---- gate 1 (recording active) classification --------------------------------

def test_recording_start():
    rec, mid = classify_recording_message(_recording_msg(True))
    assert rec is True
    assert mid == "mtg-internal-1"


def test_recording_pause():
    rec, mid = classify_recording_message(_recording_msg(False))
    assert rec is False
    assert mid == "mtg-internal-1"


def test_recording_non_recording_message_ignored():
    assert classify_recording_message(_persist_msg(
        "RemoteDesktop", "remote-desktop-share-start")) == (None, None)


def test_recording_missing_bool_ignored():
    msg = _recording_msg(True)
    del msg["core"]["body"]["recording"]
    assert classify_recording_message(msg) == (None, None)


def test_recording_malformed_ignored():
    assert classify_recording_message({}) == (None, None)
    assert classify_recording_message({"core": "notadict"}) == (None, None)


def test_gate1_pause_resume_sequence():
    """The core bug: a pause must flip gate 1 false; a resume must flip it
    back true; start/pause/resume/stop each drive exactly one transition."""
    changes = []
    w = AkkaEventWatcher({"channels": ["c"]}, {"name": "RemoteDesktop"},
                         on_recording_change=lambda mid, r: changes.append((mid, r)))
    assert w.is_recording("m1") is False
    w.handle_raw(json.dumps(_recording_msg(True, "m1")))    # start
    assert w.is_recording("m1") is True
    w.handle_raw(json.dumps(_recording_msg(True, "m1")))    # dup start = no txn
    w.handle_raw(json.dumps(_recording_msg(False, "m1")))   # PAUSE
    assert w.is_recording("m1") is False
    w.handle_raw(json.dumps(_recording_msg(True, "m1")))    # RESUME
    assert w.is_recording("m1") is True
    w.handle_raw(json.dumps(_recording_msg(False, "m1")))   # STOP
    assert w.is_recording("m1") is False
    assert changes == [("m1", True), ("m1", False), ("m1", True), ("m1", False)]


def test_gate1_seed_and_event_override():
    """Startup seeding from getMeetings is best-effort and is overridden by a
    real event; re-seeding after an event is a no-op."""
    w = AkkaEventWatcher({"channels": ["c"]}, {"name": "RemoteDesktop"})
    # seed true (meeting appears to be recording)
    w.seed_recording("m1", True)
    assert w.is_recording("m1") is True
    # re-seed with a different value is ignored (only first-seen seeds)
    w.seed_recording("m1", False)
    assert w.is_recording("m1") is True
    # a real pause event overrides the seed...
    w.handle_raw(json.dumps(_recording_msg(False, "m1")))
    assert w.is_recording("m1") is False
    # ...and a later seed (e.g. next getMeetings poll) does NOT clobber it
    w.seed_recording("m1", True)
    assert w.is_recording("m1") is False


def test_gate1_seed_false_then_event_start():
    w = AkkaEventWatcher({"channels": ["c"]}, {"name": "RemoteDesktop"})
    w.seed_recording("m1", False)
    assert w.is_recording("m1") is False
    w.handle_raw(json.dumps(_recording_msg(True, "m1")))
    assert w.is_recording("m1") is True


def test_forget_clears_state():
    w = AkkaEventWatcher({"channels": ["c"]}, {"name": "RemoteDesktop"})
    w.handle_raw(json.dumps(_recording_msg(True, "m1")))
    w.handle_raw(json.dumps(_persist_msg("RemoteDesktop",
                                         "remote-desktop-share-start", "m1")))
    assert w.is_recording("m1") is True and w.is_sharing("m1") is True
    w.forget("m1")
    assert w.is_recording("m1") is False and w.is_sharing("m1") is False
    # after forget, seeding works again (meeting treated as first-seen)
    w.seed_recording("m1", True)
    assert w.is_recording("m1") is True


def test_share_and_recording_share_subscriber():
    """One subscriber handles both message types off the same channel."""
    w = AkkaEventWatcher({"channels": ["c"]}, {"name": "RemoteDesktop"})
    w.handle_raw(json.dumps(_recording_msg(True, "m1")))
    w.handle_raw(json.dumps(_persist_msg("RemoteDesktop",
                                         "remote-desktop-share-start", "m1")))
    assert w.is_recording("m1") is True
    assert w.is_sharing("m1") is True


def test_shareGateWatcher_alias():
    assert ShareGateWatcher is AkkaEventWatcher


def test_diff_snapshots():
    assert diff_snapshots({}, {"m1": "alice"}) == [("start", "m1", "alice")]
    assert diff_snapshots({"m1": "alice"}, {"m1": "bob"}) == \
        [("switch", "m1", "bob")]
    assert diff_snapshots({"m1": "alice"}, {}) == [("stop", "m1", "alice")]
    assert diff_snapshots({"m1": "alice"}, {"m1": "alice"}) == []


def _stub_recorder(logs, storage):
    """A Recorder wired to nothing: neither AkkaEventWatcher nor
    ScreenshareIndexer touches Redis/Postgres until started."""
    import bbb_vnc_recorder.recorder as R
    R.log = lambda *a: logs.append(" ".join(str(x) for x in a))
    cfg = {"redis": {}, "plugin": {}, "postgres": {},
           "storage": {"directory": storage},
           "vnc": {"run_dir": os.path.join(storage, "run")},  # no sockets
           "recording": {"encoding": "tight", "fps": 10, "poll_interval": 5}}
    return R.Recorder(cfg)


def test_startup_warns_when_share_state_unknowable():
    """A meeting already running when the recorder starts may have an active
    share whose start event we never saw (Redis pub/sub is not replayed, and
    gate 2 has no getMeetings equivalent to seed from).  That silently records
    nothing, so it must be reported -- once, on the first pass only."""
    logs = []
    tmp = tempfile.mkdtemp(prefix="rec-warn-")
    try:
        rec = _stub_recorder(logs, tmp)
        rec._running_meetings = lambda: {
            "mtg-1": ("ext-1", True, ["alice"]),    # recording, share unknown
        }
        rec._reconcile()
        warns = [l for l in logs if "WARNING" in l and "mtg-1" in l]
        assert len(warns) == 1, "expected one startup warning, got %r" % logs
        assert "re-share" in warns[0]

        logs.clear()
        rec._reconcile()                             # steady state: silent
        assert not [l for l in logs if "WARNING" in l], \
            "warning repeated after the first pass: %r" % logs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_startup_warning_when_share_is_known():
    """Once a share-start has been seen, there is no ambiguity to report."""
    logs = []
    tmp = tempfile.mkdtemp(prefix="rec-warn-")
    try:
        rec = _stub_recorder(logs, tmp)
        rec._running_meetings = lambda: {"mtg-1": ("ext-1", True, [])}
        rec.events.handle_raw(json.dumps(
            _persist_msg("RemoteDesktop", "remote-desktop-share-start", "mtg-1")))
        rec._reconcile()
        assert not [l for l in logs if "WARNING" in l], logs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print("ok  %s" % fn.__name__)
    print("\n%d/%d passed" % (passed, len(fns)))
    return passed, len(fns)


if __name__ == "__main__":
    p, n = _run()
    sys.exit(0 if p == n else 1)

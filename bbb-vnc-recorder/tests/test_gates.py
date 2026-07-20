"""Unit tests for gate-2 message classification and screenshare diffing.

Run: python3 -m pytest tests/  (or python3 tests/test_gates.py)
No live Redis / Postgres needed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bbb_vnc_recorder.gates import classify_message, ShareGateWatcher
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


def test_diff_snapshots():
    assert diff_snapshots({}, {"m1": "alice"}) == [("start", "m1", "alice")]
    assert diff_snapshots({"m1": "alice"}, {"m1": "bob"}) == \
        [("switch", "m1", "bob")]
    assert diff_snapshots({"m1": "alice"}, {}) == [("stop", "m1", "alice")]
    assert diff_snapshots({"m1": "alice"}, {"m1": "alice"}) == []


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

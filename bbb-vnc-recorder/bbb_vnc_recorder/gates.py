"""gates - detect the two recording gates off the akka-apps Redis bus.

Both gates are driven by messages akka-apps broadcasts on
`from-akka-apps-redis-channel`, so a single subscriber
(`AkkaEventWatcher`) tracks both:

Gate 1 (the meeting's recording is ACTIVE, i.e. not paused): tracked from
`RecordingStatusChangedEvtMsg`, whose body carries a `recording` boolean --
true on record Start/Resume, false on Pause/Stop (the moderator's "Stop
Recording" button is a *pause*, so BBB keeps the meeting's getMeetings
`<recording>` flag true across pauses; only this event reflects the real
active/paused state).  See akka-bbb-apps SetRecordingStatusCmdMsgHdlr.

Gate 2 (remote-desktop share active): tracked from the RemoteDesktop
plugin's persistEvent transitions, re-broadcast by akka as
`PluginPersistEventEvtMsg`.  The plugin emits
`remote-desktop-share-start` / `-stop` (see the bbb-plugin-remote-desktop
patch).

`classify_message` and `classify_recording_message` are pure functions so
the gate logic can be unit-tested without a live broker.
"""

import json
import threading
import time

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


def classify_message(obj, plugin_name="RemoteDesktop",
                     start_event="remote-desktop-share-start",
                     stop_event="remote-desktop-share-stop"):
    """Classify a decoded akka-apps message for gate 2 (share).

    Returns (action, meeting_id) where action is 'share-start',
    'share-stop', or None.  `obj` is the parsed JSON of a
    BbbCommonEnvCoreMsg ({"envelope": ..., "core": {"header": ...,
    "body": ...}}).
    """
    try:
        envelope = obj.get("envelope", {})
        core = obj.get("core", {})
        header = core.get("header", {})
        body = core.get("body", {})
        name = envelope.get("name") or header.get("name")
        if name != "PluginPersistEventEvtMsg":
            return (None, None)
        if body.get("pluginName") != plugin_name:
            return (None, None)
        meeting_id = header.get("meetingId")
        event_name = body.get("eventName")
        if event_name == start_event:
            return ("share-start", meeting_id)
        if event_name == stop_event:
            return ("share-stop", meeting_id)
        return (None, None)
    except AttributeError:
        return (None, None)


def classify_recording_message(obj, msg_name="RecordingStatusChangedEvtMsg"):
    """Classify a decoded akka-apps message for gate 1 (recording active).

    Returns (recording, meeting_id) where `recording` is the boolean carried
    by RecordingStatusChangedEvtMsg (true = record started/resumed, false =
    paused/stopped), or (None, None) if `obj` is not such a message.

    Envelope layout (verified against BBB 3.0 common2 msgs):
        {"envelope": {"name": "RecordingStatusChangedEvtMsg", ...},
         "core": {"header": {"name": ..., "meetingId": ..., "userId": ...},
                  "body": {"recording": bool, "setBy": str}}}
    """
    try:
        envelope = obj.get("envelope", {})
        core = obj.get("core", {})
        header = core.get("header", {})
        body = core.get("body", {})
        name = envelope.get("name") or header.get("name")
        if name != msg_name:
            return (None, None)
        recording = body.get("recording")
        if not isinstance(recording, bool):
            return (None, None)
        return (recording, header.get("meetingId"))
    except AttributeError:
        return (None, None)


class AkkaEventWatcher(threading.Thread):
    """Subscribe to the akka-apps Redis channel(s) and track both gates.

    Gate 2 (share): `is_sharing(meeting_id)` reflects the latest
    share-start/-stop.  `on_change(meeting_id, sharing)` fires on transitions.

    Gate 1 (recording active): `is_recording(meeting_id)` reflects the latest
    RecordingStatusChangedEvtMsg; `on_recording_change(meeting_id, recording)`
    fires on transitions.  Because Redis pub/sub does not replay past events, a
    recorder that starts mid-meeting won't have seen the record-Start; callers
    should `seed_recording()` a best-effort initial value (e.g. from
    getMeetings), which is used ONLY until the first real event arrives.
    """

    def __init__(self, redis_conf, plugin_conf, on_change=None,
                 on_recording_change=None, logger=None):
        super().__init__(daemon=True, name="akka-event-watcher")
        self.redis_conf = redis_conf
        self.plugin_conf = plugin_conf
        self.on_change = on_change
        self.on_recording_change = on_recording_change
        self.log = logger or (lambda *a: None)
        self._sharing = {}
        self._recording = {}
        self._recording_seen = set()   # meetings for which a real event arrived
        self._lock = threading.Lock()
        self._stopev = threading.Event()
        self._client = None

    # ---- gate 2 (share) ----------------------------------------------------

    def is_sharing(self, meeting_id):
        with self._lock:
            return self._sharing.get(meeting_id, False)

    def _apply(self, action, meeting_id):
        if not meeting_id:
            return
        new = (action == "share-start")
        with self._lock:
            old = self._sharing.get(meeting_id, False)
            self._sharing[meeting_id] = new
        if old != new:
            self.log("gate2 %s -> %s (meeting %s)" %
                     ("share" if old else "idle",
                      "share" if new else "idle", meeting_id))
            if self.on_change:
                try:
                    self.on_change(meeting_id, new)
                except Exception:  # noqa: BLE001
                    pass

    # ---- gate 1 (recording active) -----------------------------------------

    def is_recording(self, meeting_id):
        with self._lock:
            return self._recording.get(meeting_id, False)

    def seed_recording(self, meeting_id, value):
        """Best-effort initial gate-1 state (e.g. from the getMeetings
        <recording> flag) for a meeting we have not yet seen an event for.

        Idempotent and non-destructive: once a real RecordingStatusChangedEvtMsg
        has been observed for a meeting, seeding is a no-op, so the event stays
        authoritative.  NOTE: getMeetings cannot distinguish "recording" from
        "paused" (its flag stays true across pauses), so a recorder that starts
        while paused will seed true and record until the next event corrects it.
        """
        if not meeting_id:
            return
        with self._lock:
            if meeting_id in self._recording_seen or meeting_id in self._recording:
                return
            self._recording[meeting_id] = bool(value)
        self.log("gate1 seeded meeting=%s recording=%s (getMeetings, best-effort)"
                 % (meeting_id, bool(value)))

    def _apply_recording(self, recording, meeting_id):
        if not meeting_id:
            return
        with self._lock:
            old = self._recording.get(meeting_id)
            self._recording[meeting_id] = recording
            self._recording_seen.add(meeting_id)
        if old != recording:
            self.log("gate1 recording %s -> %s (meeting %s, event setBy)" %
                     (old, "active" if recording else "paused", meeting_id))
            if self.on_recording_change:
                try:
                    self.on_recording_change(meeting_id, recording)
                except Exception:  # noqa: BLE001
                    pass

    # ---- housekeeping ------------------------------------------------------

    def forget(self, meeting_id):
        """Drop all per-meeting state (call when the meeting has ended)."""
        with self._lock:
            self._sharing.pop(meeting_id, None)
            self._recording.pop(meeting_id, None)
            self._recording_seen.discard(meeting_id)

    # ---- message dispatch --------------------------------------------------

    def handle_raw(self, raw):
        """Parse one raw Redis message payload and update gate state."""
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            return
        action, meeting_id = classify_message(
            obj,
            plugin_name=self.plugin_conf.get("name", "RemoteDesktop"),
            start_event=self.plugin_conf.get("share_start_event",
                                             "remote-desktop-share-start"),
            stop_event=self.plugin_conf.get("share_stop_event",
                                            "remote-desktop-share-stop"),
        )
        if action:
            self._apply(action, meeting_id)
            return
        recording, rec_meeting = classify_recording_message(obj)
        if recording is not None:
            self._apply_recording(recording, rec_meeting)

    def run(self):
        if redis is None:
            self.log("redis module not available; gates 1+2 disabled")
            return
        channels = self.redis_conf.get("channels", ["from-akka-apps-redis-channel"])
        while not self._stopev.is_set():
            try:
                self._client = redis.Redis(
                    host=self.redis_conf.get("host", "127.0.0.1"),
                    port=self.redis_conf.get("port", 6379),
                    password=self.redis_conf.get("password") or None,
                    socket_timeout=None, socket_keepalive=True,
                    decode_responses=True,
                )
                pubsub = self._client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(*channels)
                self.log("subscribed to redis channels: %s" % ", ".join(channels))
                for msg in pubsub.listen():
                    if self._stopev.is_set():
                        break
                    if msg.get("type") != "message":
                        continue
                    self.handle_raw(msg.get("data"))
            except Exception as e:  # noqa: BLE001
                if self._stopev.is_set():
                    break
                self.log("redis subscribe error: %r; retrying in 3s" % e)
                time.sleep(3)

    def stop(self):
        self._stopev.set()
        try:
            if self._client:
                self._client.close()
        except Exception:  # noqa: BLE001
            pass


# Backwards-compatible alias: this class used to watch only gate 2.
ShareGateWatcher = AkkaEventWatcher

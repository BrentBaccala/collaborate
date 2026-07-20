"""gates - detect the two recording gates.

Gate 1 (meeting is being recorded): polled from the BBB API
(getMeetingInfo's <recording> flag); handled in recorder.py, which already
polls getMeetingInfo for the attendee list.

Gate 2 (remote-desktop share active): detected here, by subscribing to the
akka-apps Redis broadcast and watching for the RemoteDesktop plugin's
persistEvent transitions.  The plugin emits
`remote-desktop-share-start` / `-stop` (see the bbb-plugin-remote-desktop
patch); akka re-broadcasts them as PluginPersistEventEvtMsg on
`from-akka-apps-redis-channel`.

`classify_message` is a pure function so the gate logic can be unit-tested
without a live broker.
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
    """Classify a decoded akka-apps message.

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


class ShareGateWatcher(threading.Thread):
    """Subscribe to akka-apps Redis channel(s) and track per-meeting gate 2.

    `is_sharing(meeting_id)` reflects the latest share-start/-stop the meeting
    has broadcast.  `on_change(meeting_id, sharing)` is called on transitions.
    """

    def __init__(self, redis_conf, plugin_conf, on_change=None, logger=None):
        super().__init__(daemon=True, name="share-gate")
        self.redis_conf = redis_conf
        self.plugin_conf = plugin_conf
        self.on_change = on_change
        self.log = logger or (lambda *a: None)
        self._sharing = {}
        self._lock = threading.Lock()
        self._stopev = threading.Event()
        self._client = None

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

    def run(self):
        if redis is None:
            self.log("redis module not available; gate 2 disabled")
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

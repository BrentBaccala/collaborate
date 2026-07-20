"""Configuration loading for bbb-vnc-recorder."""

import copy
import os

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DEFAULT_CONFIG = {
    "storage": {
        "directory": "/var/lib/bbb-vnc-recorder",
    },
    "redis": {
        "host": "127.0.0.1",
        "port": 6379,
        "password": None,
        # akka-apps broadcasts PluginPersistEventEvtMsg on this channel (the
        # default case in FromAkkaAppsMsgSenderActor).
        "channels": ["from-akka-apps-redis-channel"],
    },
    "postgres": {
        "host": "127.0.0.1",
        "dbname": "collaborate",
        "user": "collaborate",
        "password": "collaborate",
    },
    "recording": {
        "encoding": "tight",       # tight | zrle | raw
        "fps": 10,
        "poll_interval": 5,        # seconds between BBB getMeetingInfo polls
    },
    "vnc": {
        "run_dir": "/run/vnc",
    },
    "plugin": {
        "name": "RemoteDesktop",
        "share_start_event": "remote-desktop-share-start",
        "share_stop_event": "remote-desktop-share-stop",
    },
}

CONFIG_PATH = os.environ.get("BBB_VNC_RECORDER_CONFIG",
                             "/etc/bbb-vnc-recorder/config.yml")


def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path=None):
    path = path or CONFIG_PATH
    user = {}
    if path and os.path.exists(path):
        if yaml is None:
            raise RuntimeError("PyYAML required to read %s" % path)
        with open(path) as f:
            user = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULT_CONFIG, user)

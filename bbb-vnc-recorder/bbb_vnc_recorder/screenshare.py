"""screenshare - LISTEN on the collaborate DB for grid-mode projections.

The grid-mode teacher screenshare (project_to_students in
vnc_collaborate/teacher_desktop.py) records the projected desktop in the
Postgres table collaborate.vnc_screenshare (keyed by "meetingId", value =
the projected UNIX username) and issues `NOTIFY vnc_screenshare` on every
start / switch / stop.  The NOTIFY carries no payload, so on each
notification we snapshot the whole table and diff against the previous
snapshot to derive per-meeting start/switch/stop transitions.

Each transition is appended (epoch_ms, action, screenshare_user) to a
per-meeting index alongside the FBSX files.  This is the *projection
index*, not a gate.

`diff_snapshots` is a pure function for unit testing.
"""

import json
import os
import select
import threading
import time

try:
    import psycopg2
    import psycopg2.extensions
except ImportError:  # pragma: no cover
    psycopg2 = None


def now_ms():
    return int(time.time() * 1000)


def diff_snapshots(old, new):
    """Yield (action, meeting_id, user) transitions between two snapshots.

    A snapshot is {meeting_id: screenshare_user}.  Actions:
      'start'  - meeting began projecting (absent -> present)
      'switch' - meeting changed which desktop it projects
      'stop'   - meeting stopped projecting (present -> absent)
    """
    events = []
    for mid, user in new.items():
        if mid not in old:
            events.append(("start", mid, user))
        elif old[mid] != user:
            events.append(("switch", mid, user))
    for mid, user in old.items():
        if mid not in new:
            events.append(("stop", mid, user))
    return events


class ScreenshareIndexer(threading.Thread):
    """Listen for vnc_screenshare NOTIFYs and write per-meeting index files.

    resolve_dir(meeting_id) -> directory path (or None to skip); the indexer
    appends to <dir>/screenshare.jsonl.  The recorder supplies a resolver that
    maps the table's meetingId to the recording session's storage directory
    (matching internal or external id), falling back to a directory named by
    the raw meetingId so nothing is lost.
    """

    def __init__(self, pg_conf, resolve_dir, logger=None):
        super().__init__(daemon=True, name="screenshare-index")
        self.pg_conf = pg_conf
        self.resolve_dir = resolve_dir
        self.log = logger or (lambda *a: None)
        self._stopev = threading.Event()
        self._conn = None
        self._snapshot = {}

    def _connect(self):
        conn = psycopg2.connect(
            host=self.pg_conf.get("host", "127.0.0.1"),
            dbname=self.pg_conf.get("dbname", "collaborate"),
            user=self.pg_conf.get("user", "collaborate"),
            password=self.pg_conf.get("password", "collaborate"),
        )
        conn.set_isolation_level(
            psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        return conn

    def _read_table(self):
        snap = {}
        cur = self._conn.cursor()
        try:
            cur.execute('SELECT "meetingId", screenshare FROM vnc_screenshare')
            for mid, user in cur.fetchall():
                if user is not None:
                    snap[mid] = user
        finally:
            cur.close()
        return snap

    def _emit(self, action, mid, user):
        directory = None
        try:
            directory = self.resolve_dir(mid)
        except Exception:  # noqa: BLE001
            directory = None
        if not directory:
            return
        os.makedirs(directory, exist_ok=True)
        rec = {"epoch_ms": now_ms(), "action": action,
               "screenshare_user": user, "meeting_id": mid}
        with open(os.path.join(directory, "screenshare.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
        self.log("screenshare %s meeting=%s user=%s" % (action, mid, user))

    def _handle_notify(self):
        new = self._read_table()
        for action, mid, user in diff_snapshots(self._snapshot, new):
            self._emit(action, mid, user)
        self._snapshot = new

    def run(self):
        if psycopg2 is None:
            self.log("psycopg2 not available; screenshare indexer disabled")
            return
        while not self._stopev.is_set():
            try:
                self._conn = self._connect()
                cur = self._conn.cursor()
                cur.execute("LISTEN vnc_screenshare")
                cur.close()
                self._snapshot = self._read_table()
                self.log("listening on vnc_screenshare (%d active projections)"
                         % len(self._snapshot))
                while not self._stopev.is_set():
                    if select.select([self._conn], [], [], 5) == ([], [], []):
                        continue
                    self._conn.poll()
                    had = bool(self._conn.notifies)
                    self._conn.notifies.clear()
                    if had:
                        self._handle_notify()
            except Exception as e:  # noqa: BLE001
                if self._stopev.is_set():
                    break
                self.log("screenshare listener error: %r; retrying in 3s" % e)
                time.sleep(3)
            finally:
                try:
                    if self._conn:
                        self._conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def stop(self):
        self._stopev.set()

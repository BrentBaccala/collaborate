"""recorder - the bbb-vnc-recorder service main loop.

Records the collaborate per-user VNC desktops of a meeting when BOTH gates
hold:

  Gate 1: the meeting is being recorded  (BBB getMeetingInfo <recording>).
  Gate 2: a remote-desktop share is active (ShareGateWatcher, from the
          RemoteDesktop plugin persistEvent broadcast on Redis).

While both hold, one FBSX recorder + sidecar is kept running per
participant UNIX desktop (/run/vnc/<user>), started/stopped as
participants join and leave.  A screenshare index records grid-mode
projections alongside.  Everything shares one CLOCK_REALTIME epoch-ms
clock, so cross-stream sync is a direct timestamp comparison.

Identity join key: the UNIX username, derived from a participant's BBB
fullName (fullName_to_UNIX_username).
"""

import glob
import os
import re
import signal
import sys
import threading
import time

from .config import load_config
from .fbsx import DesktopRecorder
from .gates import ShareGateWatcher
from .screenshare import ScreenshareIndexer

# Prefer the canonical mapping from the collaborate package; fall back to the
# same trivial rule (squash spaces) if it isn't importable.
try:
    from vnc_collaborate.users import fullName_to_UNIX_username
except Exception:  # noqa: BLE001
    def fullName_to_UNIX_username(full_name):
        return full_name.replace(" ", "")

try:
    import bigbluebutton
except Exception:  # noqa: BLE001
    bigbluebutton = None


def log(*args):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    sys.stdout.write("[%s] %s\n" % (ts, " ".join(str(a) for a in args)))
    sys.stdout.flush()


def rfbport_for_user(run_dir, user):
    """Best-effort lookup of the TCP rfbport for a user's Xtigervnc, by
    scanning /proc for the process bound to /run/vnc/<user>."""
    sock = os.path.join(run_dir, user)
    for cmdline_path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(cmdline_path, "rb") as f:
                args = f.read().split(b"\0")
        except OSError:
            continue
        if not args or b"Xtigervnc" not in args[0] and b"Xvnc" not in args[0]:
            continue
        argv = [a.decode("latin1", "replace") for a in args if a]
        if sock in argv:
            for i, a in enumerate(argv):
                if a == "-rfbport" and i + 1 < len(argv):
                    try:
                        return int(argv[i + 1])
                    except ValueError:
                        return None
    return None


class MeetingSession:
    """One recording session for a meeting: per-desktop recorders + storage."""

    def __init__(self, meeting_id, external_id, cfg):
        self.meeting_id = meeting_id            # BBB internal meeting id
        self.external_id = external_id
        self.cfg = cfg
        self.directory = os.path.join(cfg["storage"]["directory"], meeting_id)
        self.recorders = {}                     # unix_user -> DesktopRecorder
        self._lock = threading.Lock()
        os.makedirs(self.directory, exist_ok=True)

    def _on_recorder_exit(self, rec):
        # DesktopRecorder finished (desktop vanished or error) - drop it so a
        # later update() can restart if the desktop reappears.
        with self._lock:
            user = None
            for u, r in list(self.recorders.items()):
                if r is rec:
                    user = u
                    break
            if user is not None:
                self.recorders.pop(user, None)

    def update(self, users):
        """Ensure exactly the live desktops among `users` are being recorded."""
        run_dir = self.cfg["vnc"]["run_dir"]
        want = set()
        for user in users:
            sock = os.path.join(run_dir, user)
            if os.path.exists(sock):
                want.add(user)
        with self._lock:
            # start recorders for newly-present desktops
            for user in want:
                rec = self.recorders.get(user)
                if rec is not None and rec.is_alive():
                    continue
                sock = os.path.join(run_dir, user)
                out = os.path.join(self.directory, user + ".fbsx")
                identity = {
                    "unix_user": user,
                    "meeting_id": self.meeting_id,
                    "rfbport": rfbport_for_user(run_dir, user),
                }
                rec = DesktopRecorder(
                    sock, out, identity=identity,
                    encoding=self.cfg["recording"]["encoding"],
                    fps=self.cfg["recording"]["fps"],
                    on_exit=self._on_recorder_exit, logger=log)
                self.recorders[user] = rec
                rec.start()
            # stop recorders whose desktop left the meeting or vanished
            for user, rec in list(self.recorders.items()):
                if user not in want:
                    rec.stop()
                    self.recorders.pop(user, None)

    def stop(self):
        with self._lock:
            for rec in list(self.recorders.values()):
                rec.stop()
            self.recorders.clear()


class Recorder:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sessions = {}                      # internal meeting_id -> MeetingSession
        self._stopev = threading.Event()
        self.gate2 = ShareGateWatcher(
            cfg["redis"], cfg["plugin"], on_change=self._on_share_change,
            logger=log)
        self.screenshare = ScreenshareIndexer(
            cfg["postgres"], self._resolve_screenshare_dir, logger=log)

    # ---- screenshare dir resolution ---------------------------------------

    def _resolve_screenshare_dir(self, table_meeting_id):
        """Map the vnc_screenshare table's meetingId to a session directory.

        The desktops set their MeetingId env from BBB's meeting; match it
        against each active session's internal/external id.  If nothing
        matches, fall back to a directory named by the raw id so the
        projection index is never dropped."""
        for mid, sess in self.sessions.items():
            if table_meeting_id in (sess.meeting_id, sess.external_id):
                return sess.directory
        return os.path.join(self.cfg["storage"]["directory"], table_meeting_id)

    # ---- gate 2 callback ---------------------------------------------------

    def _on_share_change(self, meeting_id, sharing):
        # A share transition should take effect promptly rather than waiting
        # for the next poll; trigger an immediate reconcile.
        self._wake.set()

    # ---- BBB polling (gate 1 + participant list) --------------------------

    def _running_meetings(self):
        """Return {internal_id: (external_id, recording, [unix_users])}."""
        out = {}
        if bigbluebutton is None:
            return out
        try:
            meetings = bigbluebutton.getMeetings()
        except Exception as e:  # noqa: BLE001
            log("getMeetings failed: %r" % e)
            return out
        if isinstance(meetings, str):
            return out
        for m in meetings.findall(".//meeting"):
            external = m.findtext("meetingID")
            internal = m.findtext("internalMeetingID") or external
            recording = (m.findtext("recording") or "false").lower() == "true"
            users = []
            for att in m.findall(".//attendee"):
                full = att.findtext("fullName")
                if full:
                    users.append(fullName_to_UNIX_username(full))
            out[internal] = (external, recording, users)
        return out

    def _reconcile(self):
        meetings = self._running_meetings()
        active = set()
        for internal, (external, recording, users) in meetings.items():
            gate1 = recording
            gate2 = self.gate2.is_sharing(internal)
            if gate1 and gate2:
                active.add(internal)
                sess = self.sessions.get(internal)
                if sess is None:
                    log("START session meeting=%s (external=%s, %d users)"
                        % (internal, external, len(users)))
                    sess = MeetingSession(internal, external, self.cfg)
                    self.sessions[internal] = sess
                sess.update(users)
            else:
                if internal in self.sessions:
                    log("STOP session meeting=%s (gate1=%s gate2=%s)"
                        % (internal, gate1, gate2))
                    self.sessions.pop(internal).stop()
        # tear down sessions whose meeting ended
        for internal in list(self.sessions.keys()):
            if internal not in meetings:
                log("STOP session meeting=%s (meeting ended)" % internal)
                self.sessions.pop(internal).stop()

    # ---- run ---------------------------------------------------------------

    def run(self):
        self._wake = threading.Event()
        self.gate2.start()
        self.screenshare.start()
        interval = float(self.cfg["recording"]["poll_interval"])
        log("bbb-vnc-recorder started (storage=%s, encoding=%s, poll=%ss)"
            % (self.cfg["storage"]["directory"],
               self.cfg["recording"]["encoding"], interval))
        while not self._stopev.is_set():
            try:
                self._reconcile()
            except Exception as e:  # noqa: BLE001
                log("reconcile error: %r" % e)
            self._wake.wait(interval)
            self._wake.clear()
        log("shutting down")
        for sess in list(self.sessions.values()):
            sess.stop()
        self.gate2.stop()
        self.screenshare.stop()

    def stop(self, *args):
        self._stopev.set()
        if hasattr(self, "_wake"):
            self._wake.set()


def main():
    cfg = load_config()
    rec = Recorder(cfg)
    signal.signal(signal.SIGTERM, rec.stop)
    signal.signal(signal.SIGINT, rec.stop)
    rec.run()


if __name__ == "__main__":
    main()

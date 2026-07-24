#!/bin/bash
# Ensure the storage directory exists (StateDirectory also creates it, but be
# explicit for non-systemd installs and first-run before the unit starts).
mkdir -p /var/lib/bbb-vnc-recorder
chmod 0750 /var/lib/bbb-vnc-recorder

if hash systemctl >/dev/null 2>&1 && [ ! -f /.dockerenv ]; then
  systemctl daemon-reload || true
  systemctl enable bbb-vnc-recorder.service || true
  # prerm leaves a running service alone on upgrade, so "active" here means the
  # box was recording before this upgrade started.  Restart it into the new
  # code: leaving it stopped is a silent recording outage (the operator has no
  # reason to suspect an apt upgrade ended their capture).  A fresh install is
  # still left stopped -- redis/postgres/BBB may not be configured yet.
  if systemctl -q is-active bbb-vnc-recorder.service; then
    echo "bbb-vnc-recorder: service was running; restarting it into the new version."
    if systemctl restart bbb-vnc-recorder.service; then
      # The restart cannot recover gate 2: share start/stop arrive as Redis
      # pub/sub events, which are never replayed, so a remote-desktop share
      # that began before the restart is invisible to the new process.
      echo "bbb-vnc-recorder: NOTE: if a meeting is live, re-share the remote" \
           "desktop (and toggle Stop/Start Recording) so the restarted service" \
           "sees the events; it cannot recover an in-progress share on its own."
    else
      echo "bbb-vnc-recorder: WARNING: restart FAILED -- nothing is being recorded." \
           "Run: systemctl start bbb-vnc-recorder" >&2
    fi
  else
    echo "bbb-vnc-recorder: installed and enabled, but NOT started."
    echo "bbb-vnc-recorder: start it once redis/postgres/BBB are configured:" \
         "systemctl start bbb-vnc-recorder"
  fi
fi

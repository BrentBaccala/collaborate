#!/bin/bash
# $1 is "upgrade" when dpkg is replacing this package rather than removing it.
#
# Deliberately do NOTHING on upgrade.  Stopping here is what caused a silent
# recording loss in the field (2026-07-22): the service went down mid-meeting
# and nothing ever brought it back, because postinst does not auto-start.  The
# running process keeps its open part files through the unpack, and
# after-install.sh restarts it into the new code at the end -- one restart's
# worth of downtime instead of an open-ended outage.
if [ "$1" = "upgrade" ]; then
  exit 0
fi

if hash systemctl >/dev/null 2>&1 && [ ! -f /.dockerenv ]; then
  if systemctl -q is-active bbb-vnc-recorder.service; then
    systemctl stop bbb-vnc-recorder.service || true
  fi
  if systemctl is-enabled bbb-vnc-recorder.service >/dev/null 2>&1; then
    systemctl disable bbb-vnc-recorder.service || true
  fi
fi

#!/bin/bash
# $1 is "upgrade" when dpkg is replacing this package rather than removing it.
#
# Do nothing on upgrade: after-install.sh restarts the watcher into the new
# code if it was running.  Stopping here instead would leave it down for the
# whole unpack, and -- since a stopped watcher publishes no state changes --
# every injector would sit on whatever conference it last joined.
if [ "$1" = "upgrade" ]; then
  exit 0
fi

if hash systemctl >/dev/null 2>&1 && [ ! -f /.dockerenv ]; then
  if systemctl -q is-active bbb-conf-audio-watcher.service; then
    systemctl stop bbb-conf-audio-watcher.service || true
  fi
  if systemctl is-enabled bbb-conf-audio-watcher.service >/dev/null 2>&1; then
    systemctl disable bbb-conf-audio-watcher.service || true
  fi
fi

# Deliberately left behind on removal:
#   /etc/bigbluebutton/conf-audio.conf         - reinstalling reuses the same
#                                                credential instead of forcing
#                                                every user's baresip to be
#                                                re-rendered
#   FreeSWITCH directory/dialplan XML          - removing them mid-call would
#                                                drop a live injector
# Purge them by hand if you really mean it.

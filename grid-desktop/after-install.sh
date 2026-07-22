#!/bin/bash -e

# /run is tmpfs (wiped on boot); the tmpfiles.d entry recreates /run/vnc on
# every boot, but FPM packages don't get dpkg's automatic tmpfiles trigger, so
# create it now too -- otherwise the first spawn after a fresh install (with no
# reboot) hits ENOENT on /run/vnc/.USER.spawnlock and never starts a desktop.
if command -v systemd-tmpfiles >/dev/null 2>&1; then
    systemd-tmpfiles --create /usr/lib/tmpfiles.d/grid-desktop.conf || true
fi

# grid-desktop@.service is deliberately NOT enabled here.  It is a template:
# it does nothing until an administrator instantiates it for a specific user
# (systemctl enable --now grid-desktop@USER).

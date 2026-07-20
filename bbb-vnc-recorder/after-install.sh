#!/bin/bash
# Ensure the storage directory exists (StateDirectory also creates it, but be
# explicit for non-systemd installs and first-run before the unit starts).
mkdir -p /var/lib/bbb-vnc-recorder
chmod 0750 /var/lib/bbb-vnc-recorder

if hash systemctl >/dev/null 2>&1 && [ ! -f /.dockerenv ]; then
  systemctl daemon-reload || true
  systemctl enable bbb-vnc-recorder.service || true
  # Do not auto-start on install; start it explicitly (or on next boot) once
  # redis/postgres/BBB are configured:
  #   systemctl start bbb-vnc-recorder
fi

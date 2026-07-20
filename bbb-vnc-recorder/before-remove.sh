#!/bin/bash
if hash systemctl >/dev/null 2>&1 && [ ! -f /.dockerenv ]; then
  if systemctl -q is-active bbb-vnc-recorder.service; then
    systemctl stop bbb-vnc-recorder.service || true
  fi
  if systemctl is-enabled bbb-vnc-recorder.service >/dev/null 2>&1; then
    systemctl disable bbb-vnc-recorder.service || true
  fi
fi

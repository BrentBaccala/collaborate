#!/bin/bash
# Best-effort: configure the bbb_query Postgres role used by
# bbb-shared-notes.  The setup script is a no-op if BigBlueButton's
# bbb_graphql database is not yet present, so installing this package
# before BBB is harmless — admin can re-run /usr/sbin/bbb-shared-notes-setup
# after BBB install.
/usr/sbin/bbb-shared-notes-setup || true

# Lower the bbb-pads content-sync throttle so shared-notes updates reach
# *locked* viewers promptly.  bbb-pads batches pad-content diffs on a 15s
# trailing throttle by default (etherpad.update.throttle, milliseconds); for
# bbb-shared-notes pushes that 15s lag is very noticeable.  Merge a 250ms
# override into bbb-pads' local settings file (deep-merged over the shipped
# defaults by bbb-pads' config loader), preserving any other overrides.
#
# We deliberately do NOT restart bbb-pads here: a bbb-pads restart drops the
# in-memory user/pad mappings for every in-progress meeting (BBB does not
# re-register them), which breaks shared notes until each meeting is
# restarted.  The new throttle takes effect on the next bbb-pads restart.
if [ -d /etc/bigbluebutton ]; then
  python3 - <<'PY'
import json, os, sys
CFG = '/etc/bigbluebutton/bbb-pads.json'
DESIRED = 250
try:
    with open(CFG) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
except (FileNotFoundError, ValueError):
    data = {}
et = data.get('etherpad')
if not isinstance(et, dict):
    et = data['etherpad'] = {}
up = et.get('update')
if not isinstance(up, dict):
    up = et['update'] = {}
if up.get('throttle') == DESIRED:
    sys.exit(0)          # already set — no write, no restart
up['throttle'] = DESIRED
tmp = CFG + '.tmp'
with open(tmp, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
os.replace(tmp, CFG)
sys.exit(10)             # changed — signal the shell to restart bbb-pads
PY
  if [ $? -eq 10 ]; then
    echo "python3-bigbluebutton: set bbb-pads sync throttle to 250ms in" >&2
    echo "  /etc/bigbluebutton/bbb-pads.json -- run 'systemctl restart bbb-pads'" >&2
    echo "  at a quiet time to apply it (a restart drops notes tracking for any" >&2
    echo "  in-progress meeting)." >&2
  fi
fi

exit 0

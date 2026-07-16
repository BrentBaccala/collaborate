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
# Restart bbb-pads only when we actually change the value, so repeated
# installs/upgrades don't bounce the notes service.
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
    systemctl try-restart bbb-pads 2>/dev/null || true
  fi
fi

exit 0

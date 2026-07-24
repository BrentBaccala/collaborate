#!/bin/bash
# Exercise `conf-audio reconcile` -- the state machine the .path unit drives.
#
# Runs against a stub baresip and a hand-written state file, so no FreeSWITCH,
# no PulseAudio and no root are needed.  What it pins down is the behaviour
# that is easy to get wrong and expensive in production: never piling a second
# injector into a conference that already has one, and never tearing a live
# injector down just because the watcher went away.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONF_AUDIO="$HERE/../bin/conf-audio"
TMP="$(mktemp -d)"
trap 'pkill -u "$(id -u)" -f "$TMP" >/dev/null 2>&1; rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export CONF_AUDIO_CONF="$TMP/conf-audio.conf"
export CONF_AUDIO_STATE="$TMP/state.json"
export PATH="$TMP/stub:$PATH"
mkdir -p "$HOME" "$TMP/stub" "$TMP/share"

cat > "$CONF_AUDIO_CONF" <<EOF
INJECTOR_SIP_USER=vlcinject
INJECTOR_SIP_NAME="Remote Desktop Injector"
INJECTOR_SIP_PASSWORD=testpw
FREESWITCH_SIP_DOMAIN=10.0.0.1
FREESWITCH_SIP_PORT=5090
EOF

# stub baresip: stays alive so pgrep sees it, records how it was dialled.
# Deliberately NOT `exec sleep` -- exec replaces the argv, and both this test
# and conf-audio itself find the injector with `pgrep -f "baresip -f <dir>"`.
cat > "$TMP/stub/baresip" <<'EOF'
#!/bin/bash
echo "$@" >> "$HOME/.baresip/dialed"
sleep 30
EOF
chmod +x "$TMP/stub/baresip"

# the real script copies a baresip config template from /usr/share
cp "$HERE/../share/baresip.config" "$TMP/share/"
sed "s|/usr/share/bbb-conf-audio/|$TMP/share/|g" "$CONF_AUDIO" > "$TMP/conf-audio"
chmod +x "$TMP/conf-audio"
CONF_AUDIO="$TMP/conf-audio"

set_state() { printf '%s\n' "$1" > "$CONF_AUDIO_STATE"; }
running()   { pgrep -u "$(id -u)" -f "baresip -f $HOME/.baresip" >/dev/null 2>&1; }
current()   { cat "$HOME/.baresip/current-conference" 2>/dev/null; }

fail=0
check() { if [ "$2" = "$3" ]; then echo "  ok   $1: $3"; else echo "  FAIL $1: expected '$2', got '$3'"; fail=1; fi; }

echo "== no live conference, nothing running -> stays idle"
set_state '{"conference": null, "real": 0, "injector": false}'
"$CONF_AUDIO" reconcile >/dev/null
check "baresip running" "no" "$(running && echo yes || echo no)"

echo "== conference live, no injector yet -> joins"
set_state '{"conference": "78123", "real": 2, "injector": false}'
"$CONF_AUDIO" reconcile >/dev/null
sleep 0.5
check "baresip running"  "yes"   "$(running && echo yes || echo no)"
check "joined conference" "78123" "$(current)"
check "dialled"           "-f $HOME/.baresip -e /dial 78123" "$(cat "$HOME/.baresip/dialed")"

echo "== conference moves -> follows it"
set_state '{"conference": "78999", "real": 1, "injector": true}'
"$CONF_AUDIO" reconcile >/dev/null
sleep 0.5
check "joined conference" "78999" "$(current)"

echo "== conference ends -> disconnects"
set_state '{"conference": null, "real": 0, "injector": false}'
"$CONF_AUDIO" reconcile >/dev/null
check "baresip running" "no" "$(running && echo yes || echo no)"

echo "== someone else's injector is already in -> does NOT pile in"
set_state '{"conference": "78123", "real": 2, "injector": true}'
"$CONF_AUDIO" reconcile >/dev/null
sleep 0.5
check "baresip running" "no" "$(running && echo yes || echo no)"

echo "== watcher state missing while connected -> leaves it alone"
set_state '{"conference": "78123", "real": 2, "injector": false}'
"$CONF_AUDIO" reconcile >/dev/null
sleep 0.5
check "connected first" "yes" "$(running && echo yes || echo no)"
rm -f "$CONF_AUDIO_STATE"
"$CONF_AUDIO" reconcile >/dev/null
check "still connected" "yes" "$(running && echo yes || echo no)"

echo "== unparseable state while connected -> leaves it alone"
printf 'not json' > "$CONF_AUDIO_STATE"
"$CONF_AUDIO" reconcile >/dev/null
check "still connected" "yes" "$(running && echo yes || echo no)"

echo "== rendered baresip account carries the shared password"
check "accounts has password" "yes" \
    "$(grep -q 'auth_pass=testpw' "$HOME/.baresip/accounts" && echo yes || echo no)"
check "accounts is mode 600" "600" "$(stat -c '%a' "$HOME/.baresip/accounts")"

echo
[ $fail = 0 ] && echo "ALL RECONCILE TESTS PASSED" || echo "FAILURES"
exit $fail

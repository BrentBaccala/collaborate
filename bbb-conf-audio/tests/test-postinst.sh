#!/bin/bash
# Exercise the postinst against a fake filesystem and a stub systemctl.
#
# The two things worth pinning down are the ones that only bite in production:
# the SIP credential must be generated once and NEVER regenerated on upgrade
# (a rotated password would leave FreeSWITCH's directory, the config file and
# every user's rendered baresip account disagreeing), and an upgrade must not
# leave the watcher stopped (a stopped watcher publishes no state changes, so
# every injector freezes on whatever conference it last joined).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/etc/bigbluebutton" "$TMP/opt/freeswitch/etc/freeswitch" \
         "$TMP/usr/share/bbb-conf-audio" "$TMP/stub"
cp "$HERE/../freeswitch/vlcinject.xml.in" "$HERE/../freeswitch/aaa_vlcinject.xml" \
   "$TMP/usr/share/bbb-conf-audio/"

# FreeSWITCH vars.xml, so the postinst's SIP domain / port detection has
# something realistic to find (BBB puts the internal profile on 5090).
cat > "$TMP/opt/freeswitch/etc/freeswitch/vars.xml" <<'EOF'
<include>
  <X-PRE-PROCESS cmd="set" data="local_ip_v4=10.0.79.244"/>
  <X-PRE-PROCESS cmd="set" data="internal_sip_port=5090"/>
</include>
EOF

cat > "$TMP/stub/systemctl" <<'EOF'
#!/bin/bash
args=("$@"); [ "${args[0]}" = "-q" ] && args=("${args[@]:1}")
echo "systemctl ${args[*]}" >> "$SVC_LOG"
case "${args[0]}" in
  is-active)     [ "$(cat "$SVC_STATE")" = active ] ;;
  start|restart) echo active > "$SVC_STATE" ;;
  stop)          echo inactive > "$SVC_STATE" ;;
  is-enabled)    [ "$(cat "$SVC_ENABLED")" = yes ] ;;
  enable)        echo yes > "$SVC_ENABLED" ;;
  disable)       echo no > "$SVC_ENABLED" ;;
esac
EOF
chmod +x "$TMP/stub/systemctl"
export SVC_STATE="$TMP/svc-state" SVC_ENABLED="$TMP/svc-enabled" SVC_LOG="$TMP/svc-log"

# postinst paths rewritten into the fake tree; everything else runs for real
# (openssl generates the password, sed renders the XML).
sed -e "s|/etc/bigbluebutton|$TMP/etc/bigbluebutton|g" \
    -e "s|/opt/freeswitch/etc/freeswitch|$TMP/opt/freeswitch/etc/freeswitch|g" \
    -e "s|/usr/share/bbb-conf-audio|$TMP/usr/share/bbb-conf-audio|g" \
    -e "s|/usr/bin/bbb-conf-audio-watcher|$TMP/stub/watcher-reload|g" \
    "$HERE/../after-install.sh" > "$TMP/postinst"

# no FreeSWITCH running: the reload must fail gracefully, not abort the install
cat > "$TMP/stub/watcher-reload" <<'EOF'
#!/bin/bash
exit 1
EOF
chmod +x "$TMP/stub/watcher-reload"

CONF="$TMP/etc/bigbluebutton/conf-audio.conf"
DIRXML="$TMP/opt/freeswitch/etc/freeswitch/directory/default/vlcinject.xml"

fail=0
check() { if [ "$2" = "$3" ]; then echo "  ok   $1: $3"; else echo "  FAIL $1: expected '$2', got '$3'"; fail=1; fi; }

echo "== fresh install"
echo inactive > "$SVC_STATE"; echo no > "$SVC_ENABLED"; : > "$SVC_LOG"
PATH="$TMP/stub:$PATH" bash "$TMP/postinst" configure > "$TMP/out1" 2>&1
check "config generated"    "yes"  "$([ -f "$CONF" ] && echo yes || echo no)"
check "config world-readable" "644" "$(stat -c '%a' "$CONF" 2>/dev/null)"
. "$CONF"
check "password length"     "32"   "${#INJECTOR_SIP_PASSWORD}"
check "sip domain detected" "10.0.79.244" "$FREESWITCH_SIP_DOMAIN"
check "sip port detected"   "5090" "$FREESWITCH_SIP_PORT"
check "directory xml rendered" "yes" \
    "$(grep -q "value=\"$INJECTOR_SIP_PASSWORD\"" "$DIRXML" && echo yes || echo no)"
check "no placeholder left" "yes" \
    "$(grep -q '@INJECTOR_SIP_PASSWORD@' "$DIRXML" && echo no || echo yes)"
check "directory xml is 0640" "640" "$(stat -c '%a' "$DIRXML")"
check "dialplan installed"  "yes" \
    "$([ -f "$TMP/opt/freeswitch/etc/freeswitch/dialplan/public/aaa_vlcinject.xml" ] && echo yes || echo no)"
check "watcher started"     "active" "$(cat "$SVC_STATE")"
check "reload failure survived" "yes" \
    "$(grep -q 'could not reload FreeSWITCH' "$TMP/out1" && echo yes || echo no)"
check "did not enable for users" "yes" \
    "$(grep -q 'global' "$SVC_LOG" && echo no || echo yes)"

FIRST_PW="$INJECTOR_SIP_PASSWORD"

echo "== upgrade while running (credential must survive, watcher must not stay down)"
: > "$SVC_LOG"
PATH="$TMP/stub:$PATH" bash "$TMP/postinst" configure "1:1.0.0-1" > "$TMP/out2" 2>&1
unset INJECTOR_SIP_PASSWORD; . "$CONF"
check "password unchanged"  "$FIRST_PW" "$INJECTOR_SIP_PASSWORD"
check "watcher still active" "active"   "$(cat "$SVC_STATE")"
check "restarted, not left stopped" "yes" \
    "$(grep -q '^systemctl restart' "$SVC_LOG" && echo yes || echo no)"

echo "== prerm on upgrade leaves the watcher alone"
echo active > "$SVC_STATE"; : > "$SVC_LOG"
PATH="$TMP/stub:$PATH" bash "$HERE/../before-remove.sh" upgrade >/dev/null 2>&1
check "still active" "active" "$(cat "$SVC_STATE")"
check "no stop issued" "yes" "$(grep -q '^systemctl stop' "$SVC_LOG" && echo no || echo yes)"

echo "== prerm on removal stops and disables"
echo active > "$SVC_STATE"; echo yes > "$SVC_ENABLED"; : > "$SVC_LOG"
PATH="$TMP/stub:$PATH" bash "$HERE/../before-remove.sh" remove >/dev/null 2>&1
check "stopped"  "inactive" "$(cat "$SVC_STATE")"
check "disabled" "no"       "$(cat "$SVC_ENABLED")"

echo
[ $fail = 0 ] && echo "ALL POSTINST TESTS PASSED" || echo "FAILURES"
exit $fail

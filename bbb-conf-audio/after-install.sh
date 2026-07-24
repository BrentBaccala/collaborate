#!/bin/bash
# Generate the injector's SIP credential, wire it into FreeSWITCH, and start
# the watcher.  Enables nothing for any user: the per-user auto-join units ship
# disabled and are turned on per user with `conf-audio setup`.
set -u

CONF=/etc/bigbluebutton/conf-audio.conf
FS_ETC=/opt/freeswitch/etc/freeswitch
FS_VARS="$FS_ETC/vars.xml"

mkdir -p /etc/bigbluebutton

# ---------------------------------------------------------------- credential
# Generated once and never regenerated: rewriting it on every upgrade would
# rotate the password out from under a live injector and leave the FreeSWITCH
# directory and the users' baresip accounts disagreeing.
if [ ! -e "$CONF" ]; then
    # FreeSWITCH's SIP domain is its local IP, and BBB swaps the FreeSWITCH
    # port defaults so the *internal* profile is 5090.  Both are recorded in
    # the config rather than detected at run time, so an admin can correct them
    # on a box where the guess is wrong.
    domain=""
    if [ -r "$FS_VARS" ]; then
        domain=$(sed -n 's/.*local_ip_v4=\([0-9.]*\).*/\1/p' "$FS_VARS" | head -1)
    fi
    [ -n "$domain" ] || domain=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -n "$domain" ] || domain=127.0.0.1

    port=""
    if [ -r "$FS_VARS" ]; then
        port=$(sed -n 's/.*internal_sip_port=\([0-9]*\).*/\1/p' "$FS_VARS" | head -1)
    fi
    [ -n "$port" ] || port=5090

    password=$(openssl rand -hex 16)

    cat > "$CONF" <<EOF
# bbb-conf-audio: settings for the desktop-audio conference injector.
# Generated on $(date -Is) by the package's postinst; not replaced on upgrade.
#
# WORLD-READABLE ON PURPOSE.  Any user on this system may bridge their desktop
# audio into a conference, and this password is what lets them.  It is NOT the
# FreeSWITCH Event Socket password -- that one stays root-only, with
# bbb-conf-audio-watcher, because ESL is full control of FreeSWITCH.
#
# Changing INJECTOR_SIP_PASSWORD here means also updating
# $FS_ETC/directory/default/vlcinject.xml and running 'fs_cli -x reloadxml';
# reinstalling this package will not overwrite this file.

INJECTOR_SIP_USER=vlcinject
INJECTOR_SIP_NAME="Remote Desktop Injector"
INJECTOR_SIP_PASSWORD=$password
FREESWITCH_SIP_DOMAIN=$domain
FREESWITCH_SIP_PORT=$port
EOF
    chmod 0644 "$CONF"
    echo "bbb-conf-audio: generated $CONF (SIP domain $domain:$port)"
fi

# shellcheck source=/dev/null
. "$CONF"

# ------------------------------------------------------------- FreeSWITCH
if [ -d "$FS_ETC" ]; then
    install -d -m 0755 "$FS_ETC/directory/default" "$FS_ETC/dialplan/public"
    # The directory entry holds the password, so it is root-only -- unlike the
    # config above, which every user must read.
    sed "s|@INJECTOR_SIP_PASSWORD@|$INJECTOR_SIP_PASSWORD|" \
        /usr/share/bbb-conf-audio/vlcinject.xml.in \
        > "$FS_ETC/directory/default/vlcinject.xml"
    chmod 0640 "$FS_ETC/directory/default/vlcinject.xml"
    install -m 0644 /usr/share/bbb-conf-audio/aaa_vlcinject.xml \
        "$FS_ETC/dialplan/public/aaa_vlcinject.xml"

    # Reload through our own ESL client rather than `fs_cli -p <password>`:
    # a password on a command line is visible in /proc to every user on the
    # box, which would leak the ESL credential this design exists to protect.
    if /usr/bin/bbb-conf-audio-watcher --reloadxml >/dev/null 2>&1; then
        echo "bbb-conf-audio: FreeSWITCH config reloaded"
    else
        echo "bbb-conf-audio: could not reload FreeSWITCH (not running?);" \
             "run 'fs_cli -x reloadxml' when it is up"
    fi
else
    echo "bbb-conf-audio: no FreeSWITCH at $FS_ETC; skipped the server-side" \
         "config. Rerun this package's configuration after installing BBB." >&2
fi

# ----------------------------------------------------------------- systemd
if hash systemctl >/dev/null 2>&1 && [ ! -f /.dockerenv ]; then
    systemctl daemon-reload || true
    systemctl enable bbb-conf-audio-watcher.service || true
    # On upgrade prerm leaves the running watcher alone, so "active" here means
    # it was running before this upgrade; restart it into the new code.  On a
    # fresh install, start it -- it only reads FreeSWITCH state and publishes a
    # file, so there is nothing to stage or configure first.
    if systemctl -q is-active bbb-conf-audio-watcher.service; then
        systemctl restart bbb-conf-audio-watcher.service || \
            echo "bbb-conf-audio: WARNING: watcher restart FAILED; injectors" \
                 "will not follow conference changes until it is running" >&2
    else
        systemctl start bbb-conf-audio-watcher.service || \
            echo "bbb-conf-audio: watcher did not start; check" \
                 "'journalctl -u bbb-conf-audio-watcher'" >&2
    fi

    echo "bbb-conf-audio: per-user auto-join is NOT enabled by this package."
    echo "bbb-conf-audio: each user runs:  conf-audio setup"
    echo "bbb-conf-audio: and an admin runs once per user:  loginctl enable-linger <user>"
fi

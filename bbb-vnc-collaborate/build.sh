#!/bin/bash -ex

PACKAGE=bbb-vnc-collaborate
VERSION=2.4.12+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=3

#
# Clean up directories
rm -rf staging
rm -f bbb-vnc-collaborate*.deb

#
# package

mkdir -p staging/etc/bigbluebutton/nginx
cp vnc-collaborate.nginx staging/etc/bigbluebutton/nginx

mkdir -p staging/usr/lib/systemd/system
cp bbb-vnc-collaborate.service staging/usr/lib/systemd/system

mkdir -p staging/etc/default
cp bbb-vnc-collaborate.default staging/etc/default/bbb-vnc-collaborate

mkdir -p staging/usr/share/fvwm/default-config
cp fvwm-config staging/usr/share/fvwm/default-config/config

mkdir -p staging/etc/apport/blacklist.d
echo "/usr/bin/xtigervncviewer" > staging/etc/apport/blacklist.d/bbb-vnc-collaborate

CONFFILES="--deb-no-default-config-files"

# CONVENIENCE_DEPENDS="gnome-terminal,dbus-x11,chromium-browser,xournal"
#
# python3-posix-ipc is ours to declare, not python3-vnc-collaborate's: it is
# imported lazily inside get_or_add_user(), for adduser < 3.137, and we are the
# package that auto-creates users (the websockify proxy will create a UNIX
# account for an unknown participant).
#
# python3-tk is no longer listed here: it is needed to import vnc_collaborate
# at all, so it belongs to python3-vnc-collaborate, which declares it as of
# 0.0.2+20260721.
DEPENDS="grid-desktop,python3-vnc-collaborate,python3-posix-ipc,systemd-container,ssvnc,fvwm,dconf-cli,tigervnc-standalone-server(>=1.10),tigervnc-viewer(>=1.10),xdotool,socat"

#
# Build RPM package
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    --template-scripts \
    --before-install before-install.sh \
    --after-install after-install.sh \
    --before-remove before-remove.sh \
    --after-remove after-remove.sh \
    --description "Collaborative remote desktop service for BigBlueButton" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://www.github.com/BrentBaccala/collaborate/ \
    $CONFFILES -d $DEPENDS -t deb

#!/bin/bash -ex

PACKAGE=grid-desktop
VERSION=1.0.0+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=1

#
# Clean up directories
rm -rf staging
rm -f grid-desktop*.deb

#
# package

mkdir -p staging/usr/lib/systemd/system
cp 'grid-desktop@.service' staging/usr/lib/systemd/system

# /run/vnc must exist before the first desktop spawn (see the .tmpfiles file).
# This package owns it, because it is the one that can be installed alone:
# bbb-vnc-collaborate depends on us and so inherits it.
mkdir -p staging/usr/lib/tmpfiles.d
cp grid-desktop.tmpfiles staging/usr/lib/tmpfiles.d/grid-desktop.conf

# What it actually takes to spawn a desktop, and nothing more.
#
# python3-vnc-collaborate for ensure_vnc_server, systemd-container for
# machinectl, tigervnc for the server.  flock is util-linux (essential).
#
# tkinter is needed at import time (the vnc_collaborate __init__ imports
# teacher_desktop), but it is python3-vnc-collaborate's job to declare that,
# and as of 0.0.2+20260721 it does -- so we don't repeat it here.
#
# NOT python3-posix-ipc, despite bbb-vnc-collaborate declaring it: it is
# imported lazily inside get_or_add_user(), on the auto-create-user path, and
# only for adduser < 3.137.  ensure_vnc_server never reaches it, and the code
# comments that it "might not have posix_ipc installed".
#
# Deliberately NOT here: postgresql, nginx, fvwm, ssvnc, xdotool, socat.  Those
# belong to the BBB-side proxy in bbb-vnc-collaborate, and requiring them is
# what made that package unusable on a plain remote desktop host.
DEPENDS="python3-vnc-collaborate,systemd-container,tigervnc-standalone-server(>=1.10)"

# The unit moved here out of bbb-vnc-collaborate 2.4.10, which briefly shipped
# it; Replaces lets dpkg hand the file over without a conflict.
REPLACES="bbb-vnc-collaborate (<< 3:2.4.11)"

#
# Build deb package
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    --after-install after-install.sh \
    --description "VNC desktop systemd unit: bring up a user's desktop without them logging in" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://www.github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    --replaces "$REPLACES" \
    -t deb -d "$DEPENDS"

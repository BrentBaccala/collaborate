#!/bin/bash -ex

PACKAGE=vnc-desktop
VERSION=1.0.0+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=1

#
# Clean up directories
rm -rf staging
rm -f vnc-desktop*.deb

#
# package

mkdir -p staging/etc/tmpfiles.d
cp vnc-desktop.conf staging/etc/tmpfiles.d

mkdir -p staging/usr/lib/systemd/user
cp vnc-desktop.service staging/usr/lib/systemd/user

DEPENDS="python3-vnc-collaborate,tigervnc-standalone-server (>= 1.10)"

#
# Build deb package
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    --after-install after-install.sh \
    --description "VNC desktop service with UNIX socket in /run/vnc" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://www.github.com/BrentBaccala/collaborate/ \
    -t deb --deb-use-file-permissions -d "$DEPENDS"

#!/bin/bash -ex

PACKAGE=vnc-tunnel
VERSION=1.0.0+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=1

#
# Clean up directories
rm -rf staging
rm -f vnc-tunnel*.deb

#
# package

mkdir -p staging/etc/tmpfiles.d
cp vnc-tunnel.conf staging/etc/tmpfiles.d

mkdir -p staging/usr/lib/systemd/system
cp vnc-tunnel@.service staging/usr/lib/systemd/system

mkdir -p staging/etc/vnc-tunnel

DEPENDS="openssh-client"

#
# Build deb package
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    --after-install after-install.sh \
    --description "SSH tunnel for remote VNC desktops into /run/vnc" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://www.github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    -t deb -d "$DEPENDS"

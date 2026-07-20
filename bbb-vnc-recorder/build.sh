#!/bin/bash -ex

PACKAGE=bbb-vnc-recorder
VERSION=1.0.0+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=1

#
# Clean up
rm -rf staging
rm -f bbb-vnc-recorder*.deb

#
# Lay out the package tree
#   /usr/lib/bbb-vnc-recorder/bbb_vnc_recorder/   python package
#   /usr/bin/bbb-vnc-recorder                     service entrypoint
#   /usr/bin/fbsx-decode                          decode / verify tool
#   /usr/lib/systemd/system/bbb-vnc-recorder.service
#   /etc/bbb-vnc-recorder/config.yml
mkdir -p staging/usr/lib/bbb-vnc-recorder/bbb_vnc_recorder
cp bbb_vnc_recorder/*.py staging/usr/lib/bbb-vnc-recorder/bbb_vnc_recorder/

mkdir -p staging/usr/bin
install -m 755 bin/bbb-vnc-recorder staging/usr/bin/bbb-vnc-recorder
install -m 755 bin/fbsx-decode.py   staging/usr/bin/fbsx-decode

mkdir -p staging/usr/lib/systemd/system
cp bbb-vnc-recorder.service staging/usr/lib/systemd/system/

mkdir -p staging/etc/bbb-vnc-recorder
cp config.yml staging/etc/bbb-vnc-recorder/config.yml

# python3-bigbluebutton provides the BBB API bindings (bigbluebutton.py).
DEPENDS="python3,python3-redis,python3-psycopg2,python3-yaml,python3-bigbluebutton"

#
# Build the deb
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    -a all \
    --after-install after-install.sh \
    --before-remove before-remove.sh \
    --config-files /etc/bbb-vnc-recorder/config.yml \
    --description "Per-meeting recorder for collaborate VNC desktops (raw-RFB FBSX)" \
    --vendor freesoft.org -m cosine@freesoft.org \
    --url https://www.github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    -t deb -d "$DEPENDS"

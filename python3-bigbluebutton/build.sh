#!/bin/bash -ex

VERSION=2.4.9+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=3

rm -rf staging

mkdir -p staging
python3 setup.py install --root=staging --prefix=/usr --install-layout=deb --no-compile

mkdir -p staging/usr/sbin
install -m 755 bbb-shared-notes-setup staging/usr/sbin/

DEPENDS="python3-requests,python3-lxml,python3-pyjavaproperties"

rm -f python3-bigbluebutton*.deb
fpm -s dir -C ./staging -n python3-bigbluebutton \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    -a all \
    --description "Big Blue Button API bindings" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    --after-install after-install.sh \
    -d "$DEPENDS" -t deb

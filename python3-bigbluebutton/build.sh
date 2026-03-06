#!/bin/bash -ex

VERSION=2.4.9+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=3

rm -rf staging

mkdir -p staging
python3 setup.py install --root=staging --prefix=/usr --install-layout=deb --no-compile


# pyjavaproperties and fnvhash are PyPI-only packages (no Debian equivalent);
# they get installed via pip in the after-install script
DEPENDS="python3-pip,python3-requests,python3-lxml"

rm -f python3-bigbluebutton*.deb
fpm -s dir -C ./staging -n python3-bigbluebutton \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    -a all \
    --description "Big Blue Button API bindings" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    -d "$DEPENDS" -t deb

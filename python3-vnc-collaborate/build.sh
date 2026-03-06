#!/bin/bash -ex

TARGET=`basename $(pwd)`
VERSION=0.0.2+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=0

rm -rf staging

mkdir -p staging
cd ..
python3 setup.py install --root=python3-vnc-collaborate/staging --prefix=/usr --install-layout=deb --no-compile
cd python3-vnc-collaborate


DEPENDS="python3-bigbluebutton,python3-lxml,python3-psutil,python3-service-identity,python3-vncdotool,python3-websockify,python3-psycopg2"

rm -f python3-vnc-collaborate*.deb
fpm -s dir -C ./staging -n python3-vnc-collaborate \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    -a all \
    --description "Scripts to facilitate VNC remote desktop collaboration" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    -d "$DEPENDS" -t deb

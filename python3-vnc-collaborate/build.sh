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


# python3-tk: `import vnc_collaborate` runs the package __init__, which imports
# teacher_desktop, which imports tkinter -- so the module does not import at all
# without it.  Verified against sys.modules after a real import, not by grep.
#
# It was missing here for a long time without visible breakage, because
# dependents (bbb-vnc-collaborate) declared it themselves and because
# python3-vncdotool -> python3-pil *can* reach python3-tk via
# python3-pil.imagetk.  That path is not reliable: python3-pil's dependency is
# the alternative `mime-support | python3-pil.imagetk`, and apt satisfies the
# first branch, so a fresh install pulls mime-support and no tkinter.
#
# python3-posix-ipc is deliberately NOT here: it is imported lazily inside
# get_or_add_user(), and only for adduser < 3.137.  It belongs to whoever
# actually auto-creates users -- bbb-vnc-collaborate -- which declares it.
DEPENDS="python3-bigbluebutton,python3-lxml,python3-psutil,python3-service-identity,python3-vncdotool,python3-websockify,python3-psycopg2,python3-tk"

rm -f python3-vnc-collaborate*.deb
fpm -s dir -C ./staging -n python3-vnc-collaborate \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    -a all \
    --description "Scripts to facilitate VNC remote desktop collaboration" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    -d "$DEPENDS" -t deb

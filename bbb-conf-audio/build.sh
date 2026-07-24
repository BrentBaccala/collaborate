#!/bin/bash -ex

PACKAGE=bbb-conf-audio
VERSION=1.0.0+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=1

#
# Clean up
rm -rf staging
rm -f bbb-conf-audio*.deb

#
# Lay out the package tree
#   /usr/bin/bbb-conf-audio-watcher                 system daemon (holds ESL pw)
#   /usr/bin/conf-audio                             per-user CLI + reconcile
#   /usr/lib/systemd/system/bbb-conf-audio-watcher.service
#   /usr/lib/systemd/user/conf-audio-autojoin.{path,service}
#   /usr/share/bbb-conf-audio/                      templates the postinst and
#                                                   `conf-audio setup` install
mkdir -p staging/usr/bin
install -m 755 bin/bbb-conf-audio-watcher staging/usr/bin/bbb-conf-audio-watcher
install -m 755 bin/conf-audio             staging/usr/bin/conf-audio

mkdir -p staging/usr/lib/systemd/system
cp systemd/bbb-conf-audio-watcher.service staging/usr/lib/systemd/system/

# /usr/lib/systemd/user is the system-wide location for *user* units.  Shipping
# here (rather than into each ~/.config/systemd/user) is what makes this a
# system package that is nonetheless enabled per user -- `systemctl --global
# enable` is deliberately NOT used, since that would turn it on for everybody.
mkdir -p staging/usr/lib/systemd/user
cp systemd/conf-audio-autojoin.path    staging/usr/lib/systemd/user/
cp systemd/conf-audio-autojoin.service staging/usr/lib/systemd/user/

mkdir -p staging/usr/share/bbb-conf-audio
cp freeswitch/vlcinject.xml.in    staging/usr/share/bbb-conf-audio/
cp freeswitch/aaa_vlcinject.xml   staging/usr/share/bbb-conf-audio/
cp share/baresip.config           staging/usr/share/bbb-conf-audio/
cp share/conf-audio.pa            staging/usr/share/bbb-conf-audio/

# baresip does the SIP/RTP; openssl generates the credential in postinst.
# python3 is the watcher and the state parsing in conf-audio.
# Deliberately NOT depending on bigbluebutton/freeswitch packages: the postinst
# degrades gracefully when FreeSWITCH is absent, and this can be installed on a
# box before BBB is.
DEPENDS="python3,baresip,openssl,pulseaudio-utils"

#
# Build the deb
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    -a all \
    --after-install after-install.sh \
    --before-remove before-remove.sh \
    --description "Bridge a Linux desktop's audio into a BigBlueButton conference (SIP injector)" \
    --vendor freesoft.org -m cosine@freesoft.org \
    --url https://www.github.com/BrentBaccala/collaborate/ \
    --deb-no-default-config-files \
    -t deb -d "$DEPENDS"

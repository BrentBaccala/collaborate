#!/bin/bash -ex

TARGET=`basename $(pwd)`
BUILD=$1

PACKAGE=$(echo $TARGET | cut -d'_' -f1)
VERSION=$(echo $TARGET | cut -d'_' -f2)
DISTRO=$(echo $TARGET | cut -d'_' -f3)
TAG=$(echo $TARGET | cut -d'_' -f4)

#
# Clean up directories
rm -rf staging

#
# package

mkdir -p staging/etc/bigbluebutton/nginx
cp auth-jwt.nginx staging/etc/bigbluebutton/nginx

mkdir -p staging/usr/lib/systemd/system
cp bbb-auth-jwt.service staging/usr/lib/systemd/system

mkdir -p staging/usr/share/bbb-auth-jwt
cp bbb-auth-jwt staging/usr/share/bbb-auth-jwt

mkdir -p staging/usr/bin
cp bbb-mklogin staging/usr/bin

##

. ./opts-$DISTRO.sh

#
# Build RPM package
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    --after-install after-install.sh \
    --before-remove before-remove.sh \
    --description "JSON web token based authentication service for BigBlueButton" \
    $DIRECTORIES \
    $OPTS

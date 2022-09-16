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

mkdir -p staging/usr/lib/systemd/system
cp bbb-aws-hibernate.service staging/usr/lib/systemd/system

mkdir -p staging/etc/default
cp bbb-aws-hibernate.default staging/etc/default/bbb-aws-hibernate

mkdir -p staging/usr/share/bbb-aws-hibernate
cp bbb-aws-hibernate staging/usr/share/bbb-aws-hibernate

##

. ./opts-$DISTRO.sh

#
# Build RPM package
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    --after-install after-install.sh \
    --before-remove before-remove.sh \
    --description "Automatic hibernation service" \
    $DIRECTORIES \
    $OPTS

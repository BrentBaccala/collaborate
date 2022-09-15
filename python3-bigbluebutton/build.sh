#!/bin/bash -ex
#
# DEPENDENCIES
#
# We have several packages we depend on, some of which exist only in
# the Debian archive (apt) and some of which exist only in the PyPI
# archive (pip3).
#
# Debian packages (listed in the package dependencies)
# python3-pip    - required to use pip in the post-install script
# python3-requests
# python3-lxml
#
# PyPI packages (installed with pip in the post-install script)
# pyjavaproperties
# fnvhash

TARGET=`basename $(pwd)`
BUILD=$1

PACKAGE=$(echo $TARGET | cut -d'_' -f1)
VERSION=$(echo $TARGET | cut -d'_' -f2)
DISTRO=$(echo $TARGET | cut -d'_' -f3)
TAG=$(echo $TARGET | cut -d'_' -f4)

# Should move this into the docker image
#
# There's a Dockerfile in this directory that will add these packages
# to the standard build image, and then these commands here become
# NO-OPs.

apt update
DEBIAN_FRONTEND=noninteractive apt -y upgrade
apt install -y python3-all python3-pip
pip3 install setuptools stdeb

# This is so broken because there's some kind of bug in stdeb that
# prevents us from including post install scripts, so we re-build
# the (edited) package.
#
# See https://github.com/astraw/stdeb/issues/132
#
# Plus, the --depends switch doesn't work as documented, so we manually insert
# the dependency before rebuilding the package.
#
# Plus, Debian version numbers are incompatible with Python version
# numbers (due to the presence of the tilde sign), so stdeb modifies
# the version number to conform to Python standards.  We edit the
# changelog before re-building the package in order to change it back.

python3 setup.py --command-packages=stdeb.command bdist_deb

rm -r deb_dist/bigbluebutton-*/bigbluebutton.egg-info
rm deb_dist/*.deb
cp debian/* deb_dist/bigbluebutton-*/debian/
sed -i '/^Depends:/s/$/,python3-pip,python3-requests,python3-lxml,python3-pymongo/' deb_dist/bigbluebutton-*/debian/control
sed -i "/^bigbluebutton/s/(.*)/($EPOCH:$VERSION)/" deb_dist/bigbluebutton-*/debian/changelog
( cd deb_dist/bigbluebutton-*; dpkg-buildpackage -b )

cp deb_dist/*.deb .

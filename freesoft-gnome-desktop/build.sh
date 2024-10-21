#!/bin/bash -ex

PACKAGE=freesoft-gnome-desktop
VERSION=2.4.9+$(git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')
BUILD=1
EPOCH=3

#
# Clean up directories
rm -rf staging

#
# package

mkdir -p staging/etc/dconf/profile/
cp user staging/etc/dconf/profile/

mkdir -p staging/etc/dconf/db/local.d/
cp 10freesoft staging/etc/dconf/db/local.d/
cp 20disable-screen-lock staging/etc/dconf/db/local.d/

# these are here to set new users to store Chromium passwords unencrypted,
# which has to be done to prevent constant annoying password prompts
mkdir -p staging/etc/skel/.local/share/keyrings/
cp default staging/etc/skel/.local/share/keyrings/
cp Default_keyring.keyring staging/etc/skel/.local/share/keyrings/

# this disables gnome's initial setup dialog for new users
mkdir -p staging/etc/skel/.config
cp gnome-initial-setup-done staging/etc/skel/.config

##

# ubuntu-desktop is a package with nothing but dependencies
# ubuntu-desktop's recommends include gnome-initial-setup

# I'd like to install ubuntu-desktop, but without gnome-initial-setup, or arrange to disable gnome-initial-setup

# Also install gnome-shell-extensions and gnome-shell-extension-dash-to-panel

# Ubuntu 24 has dropped gnome-shell-extension-dash-to-panel
#    https://askubuntu.com/questions/1511881/shell-extension-manager-errors-on-ubuntu-24-04
# but I'm not running on Ubuntu 24 because
#    1. BigBlueButton doesn't run on Ubuntu 24 (so we'd need a separate remote desktop server) and
#    2. gnome-terminal in a vnc desktop seems to be broken

DEPENDS=ubuntu-desktop,gnome-shell-extensions,gnome-shell-extension-dash-to-panel

#
# Build RPM package
fpm -s dir -C ./staging -n $PACKAGE \
    --version $VERSION --iteration $BUILD --epoch $EPOCH \
    --after-install after-install.sh \
    --description "The freesoft.org desktop system" \
    --vendor freesoft.org -m cosine@freesoft.org --url https://www.github.com/BrentBaccala/collaborate/ \
    -t deb --deb-use-file-permissions --depends $DEPENDS

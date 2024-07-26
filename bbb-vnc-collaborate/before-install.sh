#!/bin/bash -e

# I'd like to pick up PACKAGE from build.sh, but this is simpler
PACKAGE=bbb-vnc-collaborate
DIVERT_FILE=/usr/share/fvwm/default-config/config

if [[ $(dpkg-divert --listpackage $DIVERT_FILE) != $PACKAGE ]]; then
    dpkg-divert --package $PACKAGE --add --rename \
        --divert $DIVERT_FILE.dist $DIVERT_FILE
fi

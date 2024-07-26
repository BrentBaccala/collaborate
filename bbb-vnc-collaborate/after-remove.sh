#!/bin/bash -e

# I'd like to pick up PACKAGE from build.sh, but this is simpler
PACKAGE=bbb-vnc-collaborate
DIVERT_FILE=/usr/share/fvwm/default-config/config

if [ remove = "$1" -o abort-install = "$1" -o disappear = "$1" ]; then
    dpkg-divert --package $PACKAGE --remove --rename \
        --divert $DIVERT_FILE.dist $DIVERT_FILE
fi

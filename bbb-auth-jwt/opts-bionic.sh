. ./opts-global.sh

CONFFILES="--deb-no-default-config-files"

# python3-pip is here so we can call it in the post install script
OPTS="$OPTS $CONFFILES -d python3-jwt,python3-dateutil,python3-bigbluebutton,python3-pip -t deb --deb-use-file-permissions"


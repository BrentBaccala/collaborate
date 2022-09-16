#!/bin/bash -e

# fastcgi isn't in the apt repository, so do this instead...
if ! pip3 show -q fastcgi; then pip3 install fastcgi; fi

startService bbb-auth-jwt || echo "bbb-auth-jwt service could not be registered or started"

reloadService nginx

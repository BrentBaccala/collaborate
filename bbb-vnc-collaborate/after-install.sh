#!/bin/bash -e

# Embedded Ruby (ERB) enabled with fpm's --template-scripts option
<%= File.read('../deb-helper.sh') %>

# If Python version is less than 3.7, the python3-vnc-collaborate
# package needs the backported importlib-resources.
#
# I can't install it with the python3-vnc-collaborate package because
# something is broken in stdeb that prevents post-install scripts
# from working with stdeb-generated packages, so I install it here.
#
# (See https://github.com/astraw/stdeb/issues/132)
#
# There's also a clause in python3-vnc-collaborate's install_requires:
#     importlib_resources; python_version < "3.7"
# but it looks like stdeb can't convert this to a Debian package dependency
# (because importlib_resources doesn't have a corresponding Debian package)
# so it does nothing with it.

if ! python3  -c $'import sys\nexit(sys.version_info.minor < 7)'; then
    pip3 install importlib-resources
fi

startService bbb-vnc-collaborate || echo "bbb-vnc-collaborate service could not be registered or started"

# The bbb-vnc-collaborate package does not depend on nginx, so it might not be installed.

if [ -r /usr/sbin/nginx ]; then
    reloadService nginx
fi

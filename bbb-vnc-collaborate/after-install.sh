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

# Create PostgreSQL role and database for screenshare signaling
if runuser -u postgres -- psql -tc "SELECT 1 FROM pg_roles WHERE rolname='collaborate'" | grep -q 1; then
    echo "PostgreSQL role 'collaborate' already exists"
else
    runuser -u postgres -- psql -c "CREATE USER collaborate WITH PASSWORD 'collaborate'"
fi

if runuser -u postgres -- psql -tc "SELECT 1 FROM pg_database WHERE datname='collaborate'" | grep -q 1; then
    echo "PostgreSQL database 'collaborate' already exists"
else
    runuser -u postgres -- psql -c "CREATE DATABASE collaborate OWNER collaborate"
fi

runuser -u postgres -- psql -d collaborate -c "
CREATE TABLE IF NOT EXISTS vnc_screenshare (
    \"meetingId\" VARCHAR(100) PRIMARY KEY,
    screenshare VARCHAR(100) NOT NULL
);
ALTER TABLE vnc_screenshare OWNER TO collaborate;
"

# Configure plugin settings in bbb-html5.yml
#
# - Migrate old-style public.remoteDesktop config to public.plugins[RemoteDesktop].settings
# - Add buttons config if not present
# - Set defaults for remoteDesktopUrl and startLocked only if not already set
# - Derive remoteDesktopUrl from bigbluebutton.web.serverURL (https→wss, append /vnc)

BBB_HTML5_YML=/etc/bigbluebutton/bbb-html5.yml
BBB_WEB_PROPS=/etc/bigbluebutton/bbb-web.properties
BBB_PROPS=/usr/share/bbb-web/WEB-INF/classes/bigbluebutton.properties

SERVER_URL=$(grep -oP '(?<=^bigbluebutton.web.serverURL=).*' "$BBB_WEB_PROPS" 2>/dev/null || \
             grep -oP '(?<=^bigbluebutton.web.serverURL=).*' "$BBB_PROPS" 2>/dev/null || echo "")
VNC_URL=$(echo "$SERVER_URL" | sed 's|^https://|wss://|')/vnc

if [ -f "$BBB_HTML5_YML" ]; then
    python3 -c "
import yaml, sys

yml_path = '$BBB_HTML5_YML'
vnc_url = '$VNC_URL'

with open(yml_path) as f:
    config = yaml.safe_load(f) or {}

public = config.setdefault('public', {})

# Migrate old-style public.remoteDesktop to new plugin settings
old = public.pop('remoteDesktop', None)

plugins = public.setdefault('plugins', [])

# Find existing RemoteDesktop plugin entry
rd = None
for p in plugins:
    if isinstance(p, dict) and p.get('name') == 'RemoteDesktop':
        rd = p
        break

if rd is None:
    rd = {'name': 'RemoteDesktop', 'settings': {}}
    plugins.append(rd)

settings = rd.setdefault('settings', {})

# Migrate old settings (don't overwrite if already set in new location)
if old and isinstance(old, dict):
    if 'defaultUrl' in old and 'remoteDesktopUrl' not in settings:
        settings['remoteDesktopUrl'] = old['defaultUrl']
    if 'startLocked' in old and 'startLocked' not in settings:
        settings['startLocked'] = old['startLocked']

# Set defaults only if not already configured
if 'remoteDesktopUrl' not in settings:
    settings['remoteDesktopUrl'] = vnc_url
if 'startLocked' not in settings:
    settings['startLocked'] = False

# Add default buttons config if not present
if 'buttons' not in settings:
    settings['buttons'] = [
        {'label': 'Grid View', 'icon': 'grid-2x2', 'keysym': 65491}
    ]

with open(yml_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print('bbb-vnc-collaborate: updated plugin settings in bbb-html5.yml')
"
else
    # Create bbb-html5.yml from scratch
    python3 -c "
import yaml

vnc_url = '$VNC_URL'
config = {
    'public': {
        'plugins': [{
            'name': 'RemoteDesktop',
            'settings': {
                'remoteDesktopUrl': vnc_url,
                'startLocked': False,
                'buttons': [
                    {'label': 'Grid View', 'icon': 'grid-2x2', 'keysym': 65491}
                ]
            }
        }]
    }
}

with open('$BBB_HTML5_YML', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print('bbb-vnc-collaborate: created bbb-html5.yml with plugin settings')
"
fi

startService bbb-vnc-collaborate || echo "bbb-vnc-collaborate service could not be registered or started"

# The bbb-vnc-collaborate package does not depend on nginx, so it might not be installed.

if [ -r /usr/sbin/nginx ]; then
    reloadService nginx
fi

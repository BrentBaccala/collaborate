# A customized version of websockify that uses the websockify library,
# but replaces one method call to allow VNC Websocket connections
# to be relayed to different destinations based on the path
# specified in the URL, which should be the BBB fullName.
#
# We map the BBB fullName (or whatever path was specified) to UNIX
# users using a Postgres database whose authentication password
# is specified on the command line.
#
# If the SQL table contains an 'rfbport', we relay the connection
# to that TCP port (on localhost).  Otherwise, if the SQL table
# contains an 'UNIXuser', we relay the connection to /run/vnc/USER.
# If /run/vnc/USER doesn't exist, we start a VNC server for that
# user along with a socat listening on /run/vnc/USER.
#
# If none of this works, we fall back to the server and port specified
# on the command line as a default.
#
# On Ubuntu 16, need to install with --no-deps:
#   sudo -H pip3 install --no-deps -U websockify
# websockify would like numpy, but PyPI numpy can't run on Python less than 3.6

import sys
import os
import psutil
import glob
import urllib
import subprocess
import jwt

from . import bigbluebutton

try:
    import importlib.resources as pkg_resources
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    # need to run 'pip3 install importlib-resources' to get this
    import importlib_resources as pkg_resources

# Warning are explicitly disabled here, otherwise we'll get a
#   "no 'numpy' module, HyBi protocol will be slower"
# every time we import vnc_collaborate for anything.

import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from websockify import websocketproxy

def find_running_VNCserver(UNIXuser):
    for p in psutil.process_iter(['username', 'name', 'cmdline']):
        if p.info['username'] == UNIXuser and 'vnc' in p.info['name'] and '-rfbport' in p.info['cmdline']:
            return int(p.info['cmdline'][p.info['cmdline'].index('-rfbport') + 1])
    return None

from websockify.websocketproxy import ProxyRequestHandler

old_new_websocket_client = ProxyRequestHandler.new_websocket_client

def new_websocket_client(self):
    try:
        userID = urllib.parse.urlparse(self.path).path[1:]
    except (KeyError, IndexError):
        userID = ''

    try:
        decoded = jwt.decode(userID, bigbluebutton.securitySalt())
        fullName = decoded['sub']
    except (jwt.PyJWTError, KeyError) as err:
        print(err)
        fullName = ''

    rfbport = bigbluebutton.fullName_to_rfbport(fullName)
    UNIXuser = bigbluebutton.fullName_to_UNIX_username(fullName)

    if rfbport:

        self.server.target_host = 'localhost'
        self.server.target_port = int(rfbport)

        # Perhaps we should use BBB user IDs as the filenames in /run/vnc?
        # That would require passing them in with the JSON web tokens.
        path = '/run/vnc/' + fullName
        subprocess.run(['sudo', 'mkdir', '-p', '/run/vnc'])
        subprocess.Popen(['sudo', 'socat',
                          'UNIX-LISTEN:{},fork,group={},mode=775'.format(path, 'bigbluebutton'),
                          'TCP4:localhost:'+str(rfbport)])

    elif UNIXuser:

        if not os.path.exists('/run/vnc/' + UNIXuser):

            if os.path.exists('/usr/bin/tigervncserver'):

                # Prefer Tiger VNC if it's installed.  We don't need a custom script to disable authentication,
                # it supports the RANDR extension, and the most recent versions (not the Ubuntu 18 version)
                # support UNIX domain sockets, which will (eventually) eliminate the need for the socat below.

                # We do need to set BlacklistThreshold high, since connections with AuthType None are treated
                # as blacklistable connections, and after we've gotten five of them, the server starts rejecting
                # connections.

                subprocess.run(['sudo', '-u', UNIXuser, '-i', 'tigervncserver',
                                '-localhost', 'yes',
                                '-SecurityTypes', 'None',
                                '-BlacklistThreshold', '1000000'])

            else:

                # We use a modifed version of the tight VNC server script that starts a server with no authentication,
                # since we're providing the authentication using the JSON Web Tokens.

                tightvncserver = pkg_resources.open_binary(__package__, 'tightvncserver.pl')
                subprocess.run(['sudo', '-u', UNIXuser, '-i', 'perl'], stdin=tightvncserver)

            # Use our root sudo access to make the user's .Xauthority file readable by group 'bigbluebutton',
            # which allows the teacher to project screen shares onto the student desktop.

            subprocess.run(['sudo', 'chgrp', 'bigbluebutton', '/home/{}/.Xauthority'.format(UNIXuser)])
            subprocess.run(['sudo', 'chmod', 'g+r', '/home/{}/.Xauthority'.format(UNIXuser)])

            # I also want to allow local VNC connections, mainly for overlaying VNC viewers within
            # the VNC desktops (this is how we do things like screen shares and letting the teacher
            # observe all of the student desktops).  Since ssvncviewer will connect to a UNIX domain
            # socket, a simple solution is to start a socat to relay UNIX domain connections from a
            # socket in /run/vnc to the VNC server.  Set its group to allow teacher access.

            # XXX there's a race condition here - the Perl script vncserver has started, but it
            # might not have yet started Xvnc, which is what find_running_VNCserver looks for

            rfbport = find_running_VNCserver(UNIXuser)
            path = '/run/vnc/' + UNIXuser
            subprocess.run(['sudo', 'mkdir', '-p', '/run/vnc'])
            subprocess.Popen(['sudo', '-b', 'socat',
                              'UNIX-LISTEN:{},fork,user={},group={},mode=775'.format(path, UNIXuser, 'bigbluebutton'),
                              'TCP4:localhost:'+str(rfbport)])

        self.server.unix_target = '/run/vnc/' + UNIXuser

    # pass through to the "parent" class's version of this method
    old_new_websocket_client(self)

ProxyRequestHandler.new_websocket_client = new_websocket_client

def websockify():
    if sys.argv[0] != 'websockify':
        sys.argv.pop(0)

    # This will call WebSocketProxy; its default RequestHandlerClass
    # is ProxyRequestHandler, but we can't override
    # RequestHandlerClass at this point, so we settle for changing the
    # method inside ProxyRequestHandler.

    websocketproxy.websockify_init()

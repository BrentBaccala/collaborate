# A customized version of websockify that uses the websockify library,
# but replaces one method call to allow VNC Websocket connections
# to be relayed to different destinations based on the path
# specified in the URL, which should be a JSON Web Token.
#
# We map the subject of the JSON Web Token to UNIX users using a
# Postgres database whose authentication password is specified on the
# command line.
#
# If the SQL table contains an 'rfbport', we relay the connection
# to that TCP port (on localhost).  Otherwise, if the SQL table
# contains an 'UNIXuser', we relay the connection to /run/vnc/USER.
#
# If /run/vnc/USER doesn't exist, we start a VNC server for that
# user along with a socat listening on /run/vnc/USER.
#
# If the user has a .vncsocket in their home directory, that overrides
# /run/vnc/USER and is used instead.  If .vncsocket is a socket, then
# the connection is relayed to the program listening on the socket.
# If .vncsocket is an executable, then it is executed, with the
# permissions of USER (so it is currently implicitly setuid, and no
# check is made to ensure that it is owned by USER), and the connected
# is relayed to the program's stdin.
#
# If it is an executable, the JSON Web Token is passed to it in
# the environment variable "JWT".
#
# If it is a socket, care must be taken to ensure that this socket is
# writable by the uid running this script.
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
import time
import tempfile

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
        JWT = urllib.parse.urlparse(self.path).path[1:]
    except (KeyError, IndexError):
        JWT = ''

    try:
        decoded = jwt.decode(JWT, bigbluebutton.securitySalt())
        fullName = decoded['sub']
    except (jwt.PyJWTError, KeyError) as err:
        print(repr(err))
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

        homesocket = '/home/{}/.vncsocket'.format(UNIXuser)
        if not os.path.exists('/run/vnc/' + UNIXuser) and not os.path.exists(homesocket):

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
            # might not have yet started Xvnc, which is what find_running_VNCserver looks for.
            # The only time I've actually seen rfbport set to None is when the user didn't have
            # a home directory and the vncserver failed completely for that reason.

            rfbport = find_running_VNCserver(UNIXuser)
            if rfbport:
                path = '/run/vnc/' + UNIXuser
                subprocess.run(['sudo', 'mkdir', '-p', '/run/vnc'])
                subprocess.Popen(['sudo', '-b', 'socat',
                                  'UNIX-LISTEN:{},fork,user={},group={},mode=775'.format(path, UNIXuser, 'bigbluebutton'),
                                  'TCP4:localhost:'+str(rfbport)])
                while not os.path.exists(path):
                    time.sleep(0.1)

        if os.path.exists(homesocket):
            stat = os.stat(homesocket)
            if (stat.st_mode & ~0o777 == 0o140000):
                # If .vncsocket is a socket, relay the connection to it
                self.server.unix_target = homesocket
            else:
                # If .vncsocket is a executable, execute it and relay the connection.
                #
                # Probably should be a "sudo -u nobody" and the script has to be SUID.
                #
                # The "socat" is needed because websockify currently can't handle a pipe.
                # It needs to be modified so that it can operate like "inetd".
                socket_fn = tempfile.mktemp()
                env = os.environ
                env['JWT'] = JWT
                subprocess.Popen(["sudo", "-u", UNIXuser, "-i", "--preserve-env=JWT",
                                  "socat", "UNIX-LISTEN:" + socket_fn + ",mode=666", "EXEC:" + homesocket], env=env);
                while not os.path.exists(socket_fn):
                    time.sleep(0.1)
                self.server.unix_target = socket_fn
        else:
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

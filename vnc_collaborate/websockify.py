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
# If the user has either .vncsocket or .vncserver in their home
# directory, that overrides /run/vnc/USER and is used instead.  If
# .vncsocket is a socket, then the connection is relayed to the
# program listening on the socket.  If .vncserver is an executable,
# then it is executed, with the permissions of USER (so it is
# currently implicitly setuid, and no check is made to ensure that it
# is owned by USER), and the connected is relayed to the program's
# stdin.
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
import time
import tempfile
import pwd
import grp
import posix_ipc
import requests

import bigbluebutton

from .users import fullName_to_UNIX_username, fullName_to_rfbport

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

def get_or_add_user(UNIXuser):
    try:
        passwd_struct = pwd.getpwnam(UNIXuser)
    except KeyError:
        print(f'User {UNIXuser} does not exist; creating them')
        # There's a race condition in the system adduser script, so protect this code with a semaphore
        with posix_ipc.Semaphore('/etc.passwd', posix_ipc.O_CREAT, initial_value=1):
            subprocess.run(['sudo', 'adduser', '--force-badname', '--disabled-password', '--gecos', '', UNIXuser])
        passwd_struct = pwd.getpwnam(UNIXuser)
    return passwd_struct

def start_VNC_server(UNIXuser, rfbpath, viewOnly=False):
    r"""
    Start a VNC server as `UNIXuser`, listening for UNIX-domain VNC
    connections on `rfbpath`, optionally in `viewOnly` mode, where no
    keyboard or mouse input will be accepted.
    """

    tigervnc_version = 10

    subprocess.run(['sudo', 'mkdir', '-p', '-m', '01777', '/run/vnc'])

    if os.path.exists('/usr/bin/tigervncserver'):

        # Prefer Tiger VNC if it's installed.  We don't need a custom script to disable authentication,
        # it supports the RANDR extension, and the most recent versions (not the Ubuntu 18 version)
        # support UNIX domain sockets, which will (eventually) eliminate the need for the socat below.

        # We do need to set BlacklistThreshold high, since connections with AuthType None are treated
        # as blacklistable connections, and after we've gotten five of them, the server starts rejecting
        # connections.

        if tigervnc_version < 10:
            subprocess.run(['sudo', '-u', UNIXuser, '-i', 'tigervncserver',
                            '-localhost', 'yes',
                            '-SecurityTypes', 'None',
                            '-BlacklistThreshold', '1000000'],
                           start_new_session=True)
        else:
            # use our own tigervncserver because of a bug in the system version
            # that waits for the server to be listening on a TCP port even
            # if you requested a UNIX domain socket via "-rfbunixpath"

            # This environment variables seems to be required to get gnome-session
            # to start properly (i.e, to start at all).
            env = os.environ
            env['XDG_SESSION_TYPE'] = 'x11'

            args = ['sudo', '-u', UNIXuser, '-i', '--preserve-env=XDG_SESSION_TYPE',
                    'python3', '-m', 'vnc_collaborate', 'tigervncserver',
                    '-localhost', 'yes',
                    '-SendPrimary=0', '-SetPrimary=0',
                    '-rfbunixpath', rfbpath,
                    '-SecurityTypes', 'None',
                    '-BlacklistThreshold', '1000000']

            if (viewOnly):
                args.extend(['-AcceptPointerEvents=0', '-AcceptKeyEvents=0'])

            subprocess.run(args, start_new_session=True, env=env)

    else:

        # We use a modifed version of the tight VNC server script that starts a server with no authentication,
        # since we're providing the authentication using the JSON Web Tokens.

        tightvncserver = pkg_resources.open_binary(__package__, 'tightvncserver.pl')
        subprocess.run(['sudo', '-u', UNIXuser, '-i', 'perl'], stdin=tightvncserver, start_new_session=True)

    # I also want to allow local VNC connections, mainly for overlaying VNC viewers within
    # the VNC desktops (this is how we do things like screen shares and letting the teacher
    # observe all of the student desktops).  Since ssvncviewer will connect to a UNIX domain
    # socket, a simple solution is to start a socat to relay UNIX domain connections from a
    # socket in /run/vnc to the VNC server.  Set its group to allow teacher access.

    # XXX there's a race condition here - the Perl script vncserver has started, but it
    # might not have yet started Xvnc, which is what find_running_VNCserver looks for.
    # The only time I've actually seen rfbport set to None is when the user didn't have
    # a home directory and the vncserver failed completely for that reason.

    if tigervnc_version < 10:
        rfbport = find_running_VNCserver(UNIXuser)
        if rfbport:
            subprocess.Popen(['sudo', '-b', 'socat',
                              'UNIX-LISTEN:{},fork,user={},group={},mode=775'.format(rfbpath, UNIXuser, 'bigbluebutton'),
                              'TCP4:localhost:'+str(rfbport)],
                             start_new_session=True)
            while not os.path.exists(rfbpath):
                time.sleep(0.1)
    else:
        # Xvnc allows us to set the mode of its UNIX domain socket, but not its group,
        # so we need to wait for it to appear and adjust things accordingly
        #
        # We need the socket to be accessible to group bigbluebutton so that teachers
        # can connect to student desktops, and to allow screen shares.
        while not os.path.exists(rfbpath):
            time.sleep(0.1)
        subprocess.run(['sudo', 'chgrp', 'bigbluebutton', rfbpath])
        subprocess.run(['sudo', 'chmod', 'g+rw', rfbpath])


from websockify.websocketproxy import ProxyRequestHandler

old_new_websocket_client = ProxyRequestHandler.new_websocket_client

def new_websocket_client(self):

    url = urllib.parse.urlparse(self.path)
    querydict = urllib.parse.parse_qs(url.query)

    # querydict includes 'sessionToken'
    #
    # HTTP request to /bigbluebutton/connection/checkAuthorization
    # will return User-Id and Meeting-Id in HTTP response headers
    #
    # API call to getMeetingInfo with meetingID will return XML with attendee/userID and attendee/fullName
    #
    # or just make an API call to getMeetings.  Simplier, but returns more data

    if 'User-Id' in self.headers:
        userID = self.headers['User-Id']
        meetingID = self.headers['Meeting-Id']
    else:
        params = {'sessionToken': querydict['sessionToken']}
        response = requests.get('https://test24.freesoft.org/bigbluebutton/connection/checkAuthorization', params=params)
        # This will raise an exception if sessionToken isn't valid
        response.raise_for_status()
        userID = response['User-Id']
        meetingID = response['Meeting-Id']

    # something seems to be wrong with this API call - returns 500 Internal Server Error (Aug 26 2022)
    #meetings = bigbluebutton.getMeetingInfo(meetingID=meetingID)
    meetings = bigbluebutton.getMeetings()
    fullName = meetings.xpath('.//userID[text()=$userID]/../fullName', userID=userID)[0].text

    rfbport = fullName_to_rfbport(fullName)
    UNIXuser = fullName_to_UNIX_username(fullName)

    if rfbport:

        self.server.target_host = 'localhost'
        self.server.target_port = int(rfbport)

    elif UNIXuser and UNIXuser != "":

        # Create a new UNIX user if they don't exist already
        passwd_struct = get_or_add_user(UNIXuser)

        homesocket = passwd_struct.pw_dir + '/.vncsocket'
        homeserver = passwd_struct.pw_dir + '/.vncserver'
        rfbpath = '/run/vnc/' + UNIXuser

        if os.path.exists(homesocket) and (os.stat(homesocket).st_mode & ~0o777 == 0o140000):
            # If .vncsocket is a socket, relay the connection to it
            self.server.unix_target = homesocket
        elif os.path.exists(homeserver) and (os.stat(homeserver).st_mode & 0o111 != 0):
            # If .vncserver is a executable, execute it and relay the connection.
            #
            # Probably should be a "sudo -u nobody" and the script has to be SUID.
            #
            # The "socat" is needed because websockify currently can't handle a pipe.
            # It needs to be modified so that it can operate like "inetd".
            socket_fn = tempfile.mktemp()
            env = os.environ
            env['UserId'] = userID
            env['MeetingId'] = meetingID
            env['fullName'] = fullName
            env['UNIXuser'] = UNIXuser
            subprocess.Popen(["sudo", "-u", UNIXuser, "-i",
                              "--preserve-env=UserId", "--preserve-env=MeetingId", "--preserve-env=fullName", "--preserve-env=UNIXuser",
                              "socat", "UNIX-LISTEN:" + socket_fn + ",mode=666", "EXEC:" + homeserver], env=env);
            while not os.path.exists(socket_fn):
                time.sleep(0.1)
            self.server.unix_target = socket_fn
        else:
            # default if no .vncserver or .vncsocket exists
            # First, start a standard user desktop if none exists
            if not os.path.exists(rfbpath):
                start_VNC_server(UNIXuser, rfbpath)

            # Next, select teacher mode if user can access more than one desktop in /run/vnc
            # XXX this isn't working right because this script runs as root
            # teacher_mode = list(map(lambda fn: os.access(fn, os.W_OK), glob.glob('/run/vnc/*'))).count(True) > 1
            teacher_mode = UNIXuser in grp.getgrnam('bigbluebutton').gr_mem

            # Finally, start a dynamic VNC server running 'vnc_function'

            if teacher_mode:
                vnc_function='teacher_desktop'
            else:
                vnc_function='student_desktop'

            # The "socat" is needed because websockify currently can't handle a pipe.
            # It needs to be modified so that it can operate like "inetd".
            #
            # We add group bigbluebutton to allow the student desktop to execute screen shares,
            # not to allow the students direct accesss to that group.
            socket_fn = tempfile.mktemp()
            env = os.environ
            env['UserId'] = userID
            env['MeetingId'] = meetingID
            env['fullName'] = fullName
            # isn't this available as $USER?
            env['UNIXuser'] = UNIXuser
            command = "python3 -m vnc_collaborate tigervncserver -quiet -fg -localhost yes -SecurityTypes None -I-KNOW-THIS-IS-INSECURE -inetd -xstartup python3 -- -m vnc_collaborate {}".format(vnc_function)
            subprocess.Popen(["sudo", "-u", UNIXuser, "-g", "bigbluebutton", "-i",
                              "--preserve-env=UserId", "--preserve-env=MeetingId", "--preserve-env=fullName", "--preserve-env=UNIXuser",
                              "socat", "UNIX-LISTEN:" + socket_fn + ",mode=666", "EXEC:" + command], env=env);
            while not os.path.exists(socket_fn):
                time.sleep(0.1)
            self.server.unix_target = socket_fn

    else:

        # If this user didn't exist in the database, use a default session,
        # but a different one for each meeting, so that each meeting's screenshare
        # is separate from any others.  I expect this to become unnecessary once we can
        # do the screenshare using a VNC multiplexer instead of the current scheme.

        UNIXuser = 'default'
        rfbpath = '/run/vnc/' + meetingID

        if not os.path.exists(rfbpath):
            start_VNC_server(UNIXuser, rfbpath, viewOnly=True)
        self.server.unix_target = rfbpath

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

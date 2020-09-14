# A customized version of websockify that uses the websockify library,
# but replaces one method call to allow VNC Websocket connections
# to be relayed to different destinations based on the path
# specified in the URL, which should be the BBB fullName.
#
# We map the BBB fullName (or whatever path was specified) to UNIX
# users using a Postgres database whose authentication password
# is specified on the command line.
#
# We search the .vnc/*.pid files and the system process table to find
# VNC a server that matches the username, otherwise we fall back to
# the server and port specified on the command line as a default.
#
# On Ubuntu 16, need to install with --no-deps:
#   sudo -H pip3 install --no-deps -U websockify
# websockify would like numpy, but PyPI numpy can't run on Python less than 3.6

import sys
import psutil
import glob
import urllib
import subprocess

from . import bigbluebutton

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
        userID = urllib.parse.unquote(self.path.split('/')[1].split('?')[0])
    except IndexError:
        userID = ''

    UNIXuser = bigbluebutton.fullName_to_UNIX_username(userID)

    if UNIXuser:
        rfbport = find_running_VNCserver(UNIXuser)

        if not rfbport:
            subprocess.Popen(['sudo', '-u', UNIXuser, '-i', 'vncserver']).wait()
            rfbport = find_running_VNCserver(UNIXuser)

        if rfbport:
            self.server.target_host = 'localhost'
            self.server.target_port = int(rfbport)

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

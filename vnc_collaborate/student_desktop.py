#
# Usage: student-desktop(MAX-DIMENSION, MIN-DIMENSION)

import subprocess
import multiprocessing
import threading

import sys
import math
import time
import psutil
import re
import signal
import os
import glob
import jwt
import stat

import tkinter as tk

from lxml import etree

import bigbluebutton

import pymongo

from .simple_text import simple_text
from .vnc import get_VNC_info
from .users import fullName_to_UNIX_username, fullName_to_rfbport

# set this True to display the JSON web token at the bottom of the student desktop
# (for debugging purposes)

display_JWT = False

# xtigervncviewer is prefered for its cut-and-paste capability

VNC_VIEWER = "xtigervncviewer"

# 'processes' maps display names to a list of processes associated
# with them.  Each one will have a vncviewer and a Tk label.

processes = list()

def kill_processes(list_of_procs):
    r"""
    Kills a list of processes that were created with either
    subprocess.Popen or multiprocessing.Process
    """

    for proc in list_of_procs:
        if isinstance(proc, subprocess.Popen):
            proc.kill()
        elif isinstance(proc, multiprocessing.Process):
            proc.terminate()
            
def add_full_screen(user, viewonly=False):

    global processes

    VNC_SOCKET = '/run/vnc/' + user

    # Send/Set Primary is turned off because we just want the clipboard, not the PRIMARY selection
    # RemoteResize is turned off so that this viewer doesn't try to resize the desktop
    proc_args = [VNC_VIEWER, '-Fullscreen', '-Shared', '-RemoteResize=0',
                 '-SetPrimary=0', '-SendPrimary=0',
                 '-MenuKey=None',
                 '-geometry', '1280x720+0+0',
                 # '-Log', 'Viewport:stdout:100',
                 VNC_SOCKET]

    if viewonly:
        proc_args.insert(-1, '-ViewOnly')

    proc = subprocess.Popen(proc_args, stderr=subprocess.DEVNULL)
    processes.append(proc)
    return proc

def terminate_this_script(sig=None, frame=None):
    kill_processes(processes)
    print('processes killed', file=sys.stderr)
    sys.stderr.flush()
    # sys.exit() only exits the current thread, but we want to end the entire process
    # See https://stackoverflow.com/questions/905189
    # This os.kill sends SIGINT to the main thread, which triggers a KeyboardInterrupt
    # there.
    os.kill(os.getpid(), signal.SIGINT)

def get_global_display_geometry(screenx=None, screeny=None):

    global SCREENX, SCREENY

    if not screenx or not screeny:
        (screenx, screeny) = subprocess.run(['xdotool', 'getdisplaygeometry'],
                                            stdout=subprocess.PIPE, encoding='ascii').stdout.split()

    SCREENX = int(screenx)
    SCREENY = int(screeny)

def student_desktop(screenx=None, screeny=None):

    get_global_display_geometry(screenx, screeny)

    try:
        JWT = jwt.decode(os.environ['JWT'], verify=False)
        text = '\n'.join([str(k) + ": " + str(v) for k,v in JWT.items()])
    except Exception as ex:
        text = repr(ex)

    print('JWT', JWT, file=sys.stderr)
    sys.stderr.flush()

    if display_JWT:
        simple_text(text, SCREENX/2, SCREENY - 100)

    UNIXname = fullName_to_UNIX_username(JWT['sub'])

    # Especially if the displays all have the same geometry, we don't really need fvwm running.
    # Screenshares trigger a lot faster if fvwm isn't running.

    #args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print student_mode_fvwm_config'", "-r"]
    #fvwm = subprocess.Popen(args)

    subprocess.run(["xsetroot", "-solid", "black"])

    try:
        base_screen = add_full_screen(UNIXname)
    except Exception as ex:
        simple_text(repr(ex), SCREENX/2, SCREENY - 300)

    # Arrange to monitor the vncviewer watching the base screen to detect when it exits
    # and kill this script at that point.  This will most commonly happen when the Big
    # Blue Button client disconnects, which will kill the ephemeral Xvnc server, which
    # will kill all of the clients running on it.
    #
    # base_screen is a subprocess.Popen.  According to its documentation, its wait() method
    # operates using a busy loop, so it might be best to re-implement this code using asyncio.
    #
    # Also, when this module is enhanced to support client screens with different geometries,
    # we'll probably terminate the base_screen viewer every time a screen activates, so this
    # code will have to be revisited then.

    def monitor_base_screen(base_screen):
        base_screen.wait()
        print('base_screen vncviewer ended', file=sys.stderr)
        sys.stderr.flush()
        terminate_this_script()

    monitor_thread = threading.Thread(target = monitor_base_screen, args=(base_screen,))
    monitor_thread.start()

    # I'd like to catch these signals and kill any subprocesses before exiting this script,
    # but it's very difficult to make that work right.  Exiting the process from a thread
    # (see terminate_this_script function) is done by sending a signal to the main thread,
    # so that signal (SIGINT) can't be caught here.

    #signal.signal(signal.SIGINT, terminate_this_script)
    #signal.signal(signal.SIGTERM, terminate_this_script)

    client = pymongo.MongoClient('mongodb://127.0.1.1/')
    db = client.meteor
    db_vnc = db.vnc
    cursor = db_vnc.watch()

    screenshares = dict()

    try:
        for document in cursor:
            print(document, file=sys.stderr)
            sys.stderr.flush()
            if base_screen.poll():
                kill_processes(list(screenshares.values()))
                break
            if document['operationType'] == 'insert':
                if 'screenshare' in document['fullDocument']:
                    user = document['fullDocument']['screenshare']
                    if user not in screenshares.keys():
                        print("Adding", user, file=sys.stdout)
                        screenshares[user] = add_full_screen(user, viewonly=True)
            if document['operationType'] == 'delete':
                kill_processes(list(screenshares.values()))
                screenshares = dict()
    except KeyboardInterrupt:
        # We'll get KeyboardInterrupt from the os.kill() in terminate_this_script
        # when the user disconnects.
        sys.exit(0)

    terminate_this_script()

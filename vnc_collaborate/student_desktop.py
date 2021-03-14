#
# Usage: student-desktop(MAX-DIMENSION, MIN-DIMENSION)

import subprocess
import multiprocessing

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

# set this True to display the JSON web token at the bottom of the teacher desktop
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
            
def add_full_screen(user):

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

    proc = subprocess.Popen(proc_args, stderr=subprocess.DEVNULL)
    processes.append(proc)
    return proc

def restore_original_state():
    for procs in processes:
        kill_processes(procs)
    subprocess.run(["xsetroot", "-solid", "grey"])
    subprocess.Popen(["fvwm", "-r"])

def signal_handler(sig, frame):
    restore_original_state()
    sys.exit(0)

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

    if display_JWT:
        simple_text(text, SCREENX/2, SCREENY - 100)

    #fullName = fullName_to_UNIX_username(JWT[])
    UNIXname = 'CharlieClown'

    # Especially if the displays all have the same geometry, we don't really need fvwm running.
    # Screenshares trigger a lot faster if fvwm isn't running.

    #args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print student_mode_fvwm_config'", "-r"]
    #fvwm = subprocess.Popen(args)

    subprocess.run(["xsetroot", "-solid", "black"])
    #time.sleep(10)

    try:
        add_full_screen(UNIXname)
    except Exception as ex:
        simple_text(repr(ex), SCREENX/2, SCREENY - 300)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    client = pymongo.MongoClient('mongodb://127.0.1.1/')
    db = client.meteor
    db_vnc = db.vnc
    cursor = db_vnc.watch()

    screenshares = dict()

    for document in cursor:
        if document['operationType'] == 'insert':
            if 'screenshare' in document['fullDocument']:
                user = document['fullDocument']['screenshare']
                if user not in screenshares.keys():
                    print("Adding", user, file=sys.stdout)
                    screenshares[user] = add_full_screen(user)
        if document['operationType'] == 'delete':
            kill_processes(list(screenshares.values()))
            screenshares = dict()

    restore_original_state()

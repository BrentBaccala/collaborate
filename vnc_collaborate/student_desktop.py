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
            
def main_loop_1(user):

    global processes

    VNC_SOCKET = '/run/vnc/' + user

    if len(processes) == 0:
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


def main_loop(user):
    try:
        main_loop_1(user)
    except Exception as ex:
        simple_text(repr(ex), SCREENX/2, SCREENY - 300)

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

    args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print student_mode_fvwm_config'", "-r"]
    fvwm = subprocess.Popen(args)

    subprocess.run(["xsetroot", "-solid", "black"])
    #time.sleep(10)
    main_loop(UNIXname)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Big Blue Button currently (version 2.2.22) lacks a mechanism in its REST API
    # to get notifications when users come and go.  So we poll every second to
    # update the display until FVWM exits.

    while True:
        try:
            #fvwm.wait(timeout=1)
            time.sleep(1)
            #break
        except subprocess.TimeoutExpired:
            main_loop(UNIXname)

    restore_original_state()

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
import stat

import tkinter as tk

from lxml import etree

import bigbluebutton

import pymongo

from .simple_text import simple_text
from .vnc import get_VNC_info
from .users import fullName_to_UNIX_username, fullName_to_rfbport

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
            
def terminate_this_script(sig=None, frame=None):
    kill_processes(processes)
    print('processes killed', file=sys.stderr)
    sys.stderr.flush()
    # sys.exit() only exits the current thread, but we want to end the entire process
    # See https://stackoverflow.com/questions/905189
    # This os.kill sends SIGINT to the main thread, which triggers a KeyboardInterrupt
    # there.
    os.kill(os.getpid(), signal.SIGINT)

# Arrange to monitor a vncviewer to detect when it exits and (maybe)
# kill this script at that point.  This will most commonly happen when
# the Big Blue Button client disconnects, which will kill the
# ephemeral Xvnc server, which will kill all of the clients running on
# it.  But the vncviewer can also die because this script killed it.
# The difference between the two cases is whether the vncviewer that
# died is still current_screen.
#
# screen is a subprocess.Popen.  According to its documentation, its
# wait() method operates using a busy loop, so it might be best to
# re-implement this code using asyncio.

current_screen = None

def monitor_screen(screen):
    global processes
    global current_screen
    screen.wait()
    processes.remove(screen)
    if screen == current_screen:
        terminate_this_script()

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

    monitor_thread = threading.Thread(target = monitor_screen, args=(proc,))
    monitor_thread.start()

    processes.append(proc)
    return proc

def get_global_display_geometry(screenx=None, screeny=None):

    global SCREENX, SCREENY

    if not screenx or not screeny:
        (screenx, screeny) = subprocess.run(['xdotool', 'getdisplaygeometry'],
                                            stdout=subprocess.PIPE, encoding='ascii').stdout.split()

    SCREENX = int(screenx)
    SCREENY = int(screeny)

def get_current_screenshare(db_vnc, meetingID, default):
    mongo_doc = db_vnc.find_one({'screenshare': {'$exists': True}, 'meetingID': meetingID})
    if mongo_doc:
        return mongo_doc['screenshare']
    else:
        return default

def student_desktop(screenx=None, screeny=None):

    get_global_display_geometry(screenx, screeny)

    # isn't this the current username?
    UNIXname = os.environ['UNIXuser']

    # Especially if the displays all have the same geometry, we don't really need fvwm running.
    # Screenshares trigger a lot faster if fvwm isn't running.

    #args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print student_mode_fvwm_config'", "-r"]
    #fvwm = subprocess.Popen(args)

    subprocess.run(["xsetroot", "-solid", "black"])

    # I'd like to catch these signals and kill any subprocesses before exiting this script,
    # but it's very difficult to make that work right.  Exiting the process from a thread
    # (see terminate_this_script function) is done by sending a signal to the main thread,
    # so that signal (SIGINT) can't be caught here.

    #signal.signal(signal.SIGINT, terminate_this_script)
    #signal.signal(signal.SIGTERM, terminate_this_script)

    # We're interested in the 'screenshare' documents in the 'vnc' collection, which look like this:
    #
    # { 'screenshare': USER_TO_PROJECT, 'meetingID': BBB_MEETINGID }
    #
    # There should be no more than one of these documents per meeting.

    client = pymongo.MongoClient('mongodb://127.0.1.1/')
    db = client.meteor
    db_vnc = db.vnc

    cursor = db_vnc.watch()
    # This filter will pick up insert operations, but deletes don't have a fullDocument.
    # I could get the documentKey from the insert and use it to build a new change stream watching for a matching delete.
    # cursor = db_vnc.watch([{'$match' : {'fullDocument.meetingID': JWT['bbb-meetingID']}}])

    global current_screen

    meetingID = os.environ['MeetingId']
    try:
        current_screenshare = get_current_screenshare(db_vnc, meetingID, UNIXname)
        viewonly = (current_screenshare != UNIXname)
        current_screen = add_full_screen(current_screenshare, viewonly=viewonly)
        for document in cursor:
            print(document, file=sys.stderr)
            sys.stderr.flush()
            new_screenshare = get_current_screenshare(db_vnc, meetingID, UNIXname)
            if new_screenshare != current_screenshare:
                current_screenshare = new_screenshare
                old_screen = current_screen
                viewonly = (current_screenshare != UNIXname)
                current_screen = add_full_screen(current_screenshare, viewonly=viewonly)
                old_screen.terminate()

    except KeyboardInterrupt:
        # We'll get KeyboardInterrupt from the os.kill() in terminate_this_script
        # when the user disconnects.
        sys.exit(0)

    terminate_this_script()

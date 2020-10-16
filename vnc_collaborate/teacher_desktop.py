#
# Usage: teacher-desktop(MAX-DIMENSION, MIN-DIMENSION)

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

import tkinter as tk

from lxml import etree

from .simple_text import simple_text
from . import bigbluebutton
from .vnc import get_VNC_info

# ssvncviewer is preferred over other VNC viewers due to its ability to scale the remote
# desktop to fit in the window geometry, an essential feature for our miniaturized
# desktop views, and for its ability to connect to UNIX domain sockets.

VIEWONLY_VIEWER = "ssvncviewer"

# VALID_DISPLAYS is a list of "displays" that should appear in the teacher mode grid.
#
# "displays" can be almost anything that keys into the next set of dictionaries;
# currently we use UNIX user names.

VALID_DISPLAYS = []

# These dictionaries map "displays" to BBB full names, BBB userIDs,
# UNIX usernames, VNC UNIX domain sockets, X11 display names (suitable
# for passing as a '-display' argument), and RFB port numbers.
#
# In addition to everything in VALID_DISPLAYS, this dictionaries should
# also contain an entry for the teacher (teacher_display) themself,
# in particular the teacher's VNC_SOCKET is needed to screenshare
# the teacher's display.

NAMES = dict()
IDS = dict()
UNIXUSER = dict()
VNC_SOCKET = dict()
X11_DISPLAY = dict()
RFBPORT = dict()

# Once we've populated RFBPORT, we'll call get_VNC_info to populate
# the VNCdata dictionary that maps RFB ports to dictionaries with keys
# 'height' 'width' and 'name', which is how we know our desktop geometry.

VNCdata = None

myMeetingID = None

HOME = os.environ['HOME']

def OLD_get_VALID_DISPLAYS_and_NAMES():
    r"""
    Look at the system process table for Xtightvnc processes and match
    them to the "fullName"s of attendees in the myMeetingID meeting.
    The fullNames get converted to UNIX usernames using the VNCusers
    table in the Postgres database.  Use this information to update
    VALID_DISPLAYS (a list of X11 display names), NAMES and IDS
    (dictionaries mapping X11 display names to fullNames and userIDs).
    """

    VALID_DISPLAYS.clear()
    NAMES.clear()
    IDS.clear()

    meetingInfo = bigbluebutton.getMeetingInfo(myMeetingID)

    running_commands = list(psutil.process_iter(['cmdline']))

    for e in meetingInfo.xpath(".//attendee"):

        fullName = e.find('fullName').text
        userID = e.find('userID').text
        role = e.find('role').text

        UNIXuser = bigbluebutton.fullName_to_UNIX_username(fullName)

        if UNIXuser:
            for proc in running_commands:
                cmdline = proc.info['cmdline']
                if len(cmdline) > 0 and 'Xtightvnc' in cmdline[0]:
                    m = re.search('/home/{}/'.format(UNIXuser), ' '.join(cmdline))
                    if m:
                        # cmdline[1] is the X11 display name
                        display = cmdline[1]
                        VNC_SOCKET[display] = '/run/vnc/' + UNIXuser
                        NAMES[display] = fullName
                        IDS[display] = userID
                        UNIXUSER[display] = UNIXuser

                        # one way to do this: only moderators can observe viewers
                        #if role == 'VIEWER':
                        #    VALID_DISPLAYS.append(display)

                        # another way - observe everyone in the meeting except yourself
                        if UNIXuser != os.environ['USER']:
                            VALID_DISPLAYS.append(display)

                        # XXX we pull the screen geometry from the command line
                        #
                        # This won't work if either 1) we run on a different machine
                        # (the whole looking at the process table idea wouldn't work),
                        # or 2) the geometry is changed with xrandr
                        if '-geometry' in cmdline:
                            GEOMETRY[display] = cmdline[cmdline.index('-geometry') + 1]
                        else:
                            GEOMETRY[display] = '1024x768'

def find_X11_DISPLAYs_and_RFBPORTs():
    X11_DISPLAY.clear()
    RFBPORT.clear()
    running_commands = list(psutil.process_iter(['cmdline']))
    for proc in running_commands:
        cmdline = proc.info['cmdline']
        if len(cmdline) > 0 and '/usr/bin/X' in cmdline[0]:
            m = re.search(r'/home/(\w*)/.Xauthority', ' '.join(cmdline))
            if m:
                # cmdline[1] is the X11 display name
                # m.group(1) is the UNIX user name
                X11_DISPLAY[m.group(1)] = cmdline[1]
                if '-rfbport' in cmdline:
                    RFBPORT[m.group(1)] = int(cmdline[cmdline.index('-rfbport') + 1])

def get_VALID_DISPLAYS_and_NAMES():
    r"""
    This version of get_VALID_DISPLAY_and_NAMES shows all VNC
    desktops running on the system, except the current user's.

    It relies on those desktops having UNIX domain sockets in /run/vnc.
    """

    VALID_DISPLAYS.clear()
    NAMES.clear()
    IDS.clear()

    find_X11_DISPLAYs_and_RFBPORTs()

    # this will hang if any of our VNC displays don't respond to the VNC protocol
    global VNCdata
    if VNCdata == None:
        # get_VNC_info is not re-entrant; we can't call it twice
        VNCdata = get_VNC_info(RFBPORT.values())

    for UNIXuser in glob.glob1('/run/vnc', '*'):

        display = UNIXuser

        VNC_SOCKET[display] = '/run/vnc/' + UNIXuser

        if UNIXuser != os.environ['USER']:

            fullName = bigbluebutton.UNIX_username_to_fullName(UNIXuser)

            NAMES[display] = fullName
            IDS[display] = UNIXuser
            UNIXUSER[display] = UNIXuser

            VALID_DISPLAYS.append(display)

# 'processes' maps display names to a list of processes associated
# with them.  Each one will have a vncviewer and a Tk label.

processes = dict()

# 'locations' maps display names to their location (an integer) in the on-screen grid.

locations = dict()

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

def main_loop():

    global processes
    global locations

    get_VALID_DISPLAYS_and_NAMES()

    old_cols = math.ceil(math.sqrt(len(locations)))
    cols = math.ceil(math.sqrt(len(VALID_DISPLAYS)))

    # If the number of clients changed enough to require a resize of
    # the entire display grid, kill all of our old processes,
    # triggering a rebuild of the entire display.

    # Otherwise, kill the processes for displays that are no longer
    # valid.  This is necessary to avoid a situation where we don't
    # have enough display slots available for the VALID_DISPLAYS,
    # which would trigger an exception a little later.

    if old_cols != cols:
        for procs in processes.values():
            kill_processes(procs)
        processes.clear()
        locations.clear()
    else:
        DEAD_DISPLAYS = [disp for disp in processes.keys() if disp not in VALID_DISPLAYS]
        for disp in DEAD_DISPLAYS:
            kill_processes(processes[disp])
            processes.pop(disp)
            locations.pop(disp)

    if cols > 0:

        SCALEX = int(SCREENX/cols - .01*SCREENX)
        SCALEY = int(SCREENY/cols - .01*SCREENY)

        SCALE = str(SCALEX) + "x" + str(SCALEY)

        for display in VALID_DISPLAYS:
            if display not in processes:
                # pick the first screen location not already claimed in locations
                i = [i for i in range(len(VALID_DISPLAYS)) if i not in locations.values()][0]
                locations[display] = i

                processes[display] = []
                row = int(i/cols)
                col = i%cols
                nativex = VNCdata[RFBPORT[display]]['width']
                nativey = VNCdata[RFBPORT[display]]['height']
                geometry = str(nativex) + 'x' + str(nativey)
                scalex = SCALEX/nativex
                scaley = SCALEY/nativey
                scale = min(scalex, scaley)
                geox = int(col * SCREENX/cols + .005*SCREENX)
                geoy = int(row * SCREENY/cols + .005*SCREENY)
                offsetx = int((SCALEX - scale*nativex)/2)
                offsety = int((SCALEY - scale*nativey)/2)
                # Use the title of the window to identify these windows to the FVWM config,
                # and to pass information (their userID and display name) to teacher_zoom.
                # The title won't be displayed with our default FVWM config for teacher mode.
                title = ";".join(["TeacherViewVNC", IDS[display], display, geometry, VNC_SOCKET[display]])
                args = [VIEWONLY_VIEWER, '-viewonly', '-geometry', '+'+str(geox+offsetx)+'+'+str(geoy+offsety),
                        '-escape', 'never',
                        '-scale', str(scale),
                        '-title', title, 'unix=' + VNC_SOCKET[display]]
                processes[display].append(subprocess.Popen(args, stderr=subprocess.DEVNULL))

                processes[display].append(simple_text(NAMES[display], geox + SCREENX/cols/2, geoy))



def restore_original_state():
    for procs in processes.values():
        kill_processes(procs)
    subprocess.run(["xsetroot", "-solid", "grey"])
    subprocess.Popen(["fvwm", "-r"])

def signal_handler(sig, frame):
    restore_original_state()
    sys.exit(0)

def teacher_desktop(screenx, screeny):

    global SCREENX, SCREENY

    SCREENX = int(screenx)
    SCREENY = int(screeny)

    global myMeetingID
    myMeetingID = bigbluebutton.find_current_meeting()

    # When switching to teacher mode, we completely replace the FVWM window manager with a new
    # instance using a completely different config, then switch back to the original config
    # (using yet another new FVWM instance) when we're not.  Not ideal, but it works.

    args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print teacher_mode_fvwm_config'", "-r"]
    fvwm = subprocess.Popen(args)

    subprocess.run(["xsetroot", "-solid", "black"])
    main_loop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Big Blue Button currently (version 2.2.22) lacks a mechanism in its REST API
    # to get notifications when users come and go.  So we poll every second to
    # update the display until FVWM exits.

    while True:
        try:
            fvwm.wait(timeout=1)
            break
        except subprocess.TimeoutExpired:
            main_loop()

    restore_original_state()

def project_to_students(screenx, screeny, student_window_name = None):
    r"""
    Project the teacher's desktop to all student desktops
    """

    global myMeetingID
    myMeetingID = bigbluebutton.find_current_meeting()

    get_VALID_DISPLAYS_and_NAMES()

    teacher_display = os.environ['USER']
    screenx = int(screenx)
    screeny = int(screeny)
    display_to_project = teacher_display

    if student_window_name:
        # see comment in teacher_zoom to understand this
        args = student_window_name.replace("\\'", "'")[1:-1].split(';')
        if len(args) >= 4 and args[0] == 'TeacherViewVNC':
            STUDENT_ID = args[1]
            STUDENT_DISPLAY = args[2]
            NATIVE_GEOMETRY = args[3]
            X_VNC_SOCKET = args[4]
            display_to_project = STUDENT_DISPLAY
            (screenx, screeny) = map(int, NATIVE_GEOMETRY.split('x'))


    processes = []

    for display in VALID_DISPLAYS:

        if display != display_to_project:
            # We're projecting display_to_project (screenx/screeny) to the student screen (display/nativex/nativey)
            studentx = VNCdata[RFBPORT[display]]['width']
            studenty = VNCdata[RFBPORT[display]]['height']
            scalex = studentx/screenx
            scaley = studenty/screeny
            scale = min(scalex, scaley)
            offsetx = int((studentx - scale*screenx)/2)
            offsety = int((studenty - scale*screeny)/2)
            # This title is recognized by the FVWM config and is presented to the user
            # on top of all other windows and with no window manager decorations.
            title = "OverlayVNC"
            # We should be in the 'bigbluebutton' group, and therefore able to read the student's
            # .Xauthority files to get the keys needed to put a window on their screen.
            args = [VIEWONLY_VIEWER,
                    '-viewonly', '-geometry', '+'+str(offsetx)+'+'+str(offsety),
                    '-escape', 'never', '-display', X11_DISPLAY[display],
                    '-scale', str(scale),
                    '-title', title, 'unix=' + VNC_SOCKET[display_to_project]]
            processes.append(subprocess.Popen(args, stderr=subprocess.DEVNULL,
                                              env={'XAUTHORITY' : '/home/{}/.Xauthority'.format(UNIXUSER[display])}))

    # Now put a window up on the teacher's screen to control the projection

    window = tk.Tk()

    button = tk.Label(
        master=window,
        text="End screenshare",
        bg="cyan",
        fg="black",
    )

    button.bind("<Button-1>", lambda self: window.destroy())

    button.pack()

    window.geometry("-0+0")
    window.title("Projection Controls")
    window.wm_title("Projection Controls")

    window.update()
    window.mainloop()

    # When the window closes, end the projection

    kill_processes(processes)

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
import jwt

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
# We need:
#   - the VNC_SOCKET when showing this desktop somewhere, and to
#     query the desktop and get its geometry (for showing it somewhere)
#   - the X11_DISPLAY when showing something on this desktop
#   - the UNIXUSER when showing something (a screenshare) on this desktop (to get the .Xauthority file)
#   - the LABELS to label the desktop in teacher mode
#   - the (Big Blue Button) IDS to deaf and undeaf students
#
# In addition to everything in VALID_DISPLAYS, this dictionaries should
# also contain an entry for the teacher (teacher_display) themself,
# in particular the teacher's VNC_SOCKET is needed to screenshare
# the teacher's display.

LABELS = dict()
IDS = dict()
UNIXUSER = dict()
VNC_SOCKET = dict()
X11_DISPLAY = dict()

# Once we've populated VNC_SOCKET, we'll call get_VNC_info to populate
# the VNCdata dictionary that maps VNC sockets to dictionaries with keys
# 'height' 'width' and 'name', which is how we know our desktop geometry.

VNCdata = None

# If myMeetingID is set to a non-None value, we limit the display to
# only those users in the specified meeting.

myMeetingID = None

def get_VALID_DISPLAYS():
    r"""
    This function relies on the desktops having UNIX domain sockets in /run/vnc.
    """

    VALID_DISPLAYS.clear()
    LABELS.clear()
    IDS.clear()

    if myMeetingID:
        meetingInfo = bigbluebutton.getMeetingInfo(myMeetingID)
        for e in meetingInfo.xpath(".//attendee"):
            fullName = e.find('fullName').text
            userID = e.find('userID').text
            UNIXuser = bigbluebutton.fullName_to_UNIX_username(fullName)
            IDS[UNIXuser] = userID
            LABELS[UNIXuser] = fullName

    for UNIXuser in sorted(glob.glob1('/run/vnc', '*')):

        display = UNIXuser

        VNC_SOCKET[display] = '/run/vnc/' + UNIXuser

        if UNIXuser != 'default' and (not myMeetingID or UNIXuser in IDS.keys()):

            if display not in LABELS:
                LABELS[display] = UNIXuser
            if display not in IDS:
                IDS[display] = ""

            UNIXUSER[display] = UNIXuser

            VALID_DISPLAYS.append(display)

    # this will hang if any of our VNC displays don't respond to the VNC protocol
    global VNCdata
    if VNCdata == None:
        # get_VNC_info is not re-entrant; we can't call it twice
        VNCdata = get_VNC_info(list(VNC_SOCKET.values()))

    # Having obtained a list of VNC sockets, we now wish to query
    # those sockets to obtain their X11 display names.
    #
    # Let us first note that they may not have X11 display names, if,
    # for example, they are VNC consoles on a virtual machine running
    # in GNS3 (or qemu, or VirtualBox).  Such displays will can not,
    # in our present implementation, support screensharing, since we
    # screenshare by putting a VNC viewer on the X11 desktop and
    # configuring the window manager to overlay it on top of all other
    # windows.
    #
    # Furthermore, our tigervnc servers, by default, do not accept X11
    # protocol TCP connections (they do accept VNC protocol TCP
    # connections), but the display names they present in their VNC
    # desktop name strings use TCP protocol syntax, like this:
    #
    #     max.fios-router.home:2 (alex)
    #
    # which we convert to UNIX socket syntax by striping off
    # everything except the ":2"

    X11_DISPLAY.clear()
    for display in VALID_DISPLAYS:
        try:
            X11_DISPLAY[display] = ':' + VNCdata[VNC_SOCKET[display]]['name'].decode().split()[0].split(':')[1]
        except:
            pass

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

    get_VALID_DISPLAYS()

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
                nativex = VNCdata[VNC_SOCKET[display]]['width']
                nativey = VNCdata[VNC_SOCKET[display]]['height']
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

                processes[display].append(simple_text(LABELS[display], geox + SCREENX/cols/2, geoy))



def restore_original_state():
    for procs in processes.values():
        kill_processes(procs)
    subprocess.run(["xsetroot", "-solid", "grey"])
    subprocess.Popen(["fvwm", "-r"])

def signal_handler(sig, frame):
    restore_original_state()
    sys.exit(0)

def teacher_desktop(screenx=None, screeny=None):

    global SCREENX, SCREENY

    if not screenx or not screeny:
        (screenx, screeny) = subprocess.run(['xdotool', 'getdisplaygeometry'],
                                            stdout=subprocess.PIPE, encoding='ascii').stdout.split()

    SCREENX = int(screenx)
    SCREENY = int(screeny)

    global myMeetingID

    try:
        JWT = jwt.decode(os.environ['JWT'], verify=False)
        text = '\n'.join([str(k) + ": " + str(v) for k,v in JWT.items()])
        myMeetingID = JWT['bbb-meetingID']
    except Exception as ex:
        text = repr(ex)
    simple_text(text, SCREENX/2, SCREENY - 100)

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

    get_VALID_DISPLAYS()

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

        if display != display_to_project and display in X11_DISPLAY:
            # We're projecting display_to_project (screenx/screeny) to the student screen (display/nativex/nativey)
            studentx = VNCdata[VNC_SOCKET[display]]['width']
            studenty = VNCdata[VNC_SOCKET[display]]['height']
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

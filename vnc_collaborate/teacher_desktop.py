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
#   - the VNCdata ('height', 'width' and 'name' in a dictionary)
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
VNCdata = dict()

# myMeetingID: the Big Blue Button meeting identifier, which we fetch
# from the JSON Web Token passed in from websockify via the
# environment

myMeetingID = None

try:
    JWT = jwt.decode(os.environ['JWT'], verify=False)
    myMeetingID = JWT['bbb-meetingID']
except:
    pass

# If collaborate_display_mode is 'current_meeting' we limit the display to
# only those users in the specified meeting.

collaborate_display_mode = 'all'

def get_VALID_DISPLAYS(all_displays=None, include_default_display = False):
    r"""
    This function relies on the desktops having UNIX domain sockets in /run/vnc.
    """

    if all_displays == None:
        all_displays = (collaborate_display_mode == 'all')

    VALID_DISPLAYS.clear()
    LABELS.clear()
    IDS.clear()

    if myMeetingID:
        meetingInfo = bigbluebutton.getMeetingInfo(meetingID = myMeetingID)
        for e in meetingInfo.xpath(".//attendee"):
            fullName = e.find('fullName').text
            userID = e.find('userID').text
            UNIXuser = fullName_to_UNIX_username(fullName)
            IDS[UNIXuser] = userID
            # If multiple BBB names map to the same UNIX user (especially
            # likely for the default display), stack them vertically in the label
            if UNIXuser not in LABELS:
                LABELS[UNIXuser] = fullName
            else:
                LABELS[UNIXuser] = LABELS[UNIXuser] + '\n' + fullName

    # If we're looking at the current meeting and there are users in
    # the meeting that see the default display, include it in the grid
    if collaborate_display_mode == 'current_meeting' and None in LABELS:
        include_default_display = True

    for UNIXuser in sorted(glob.glob1('/run/vnc', '*')):

        display = UNIXuser

        vnc_socket = '/run/vnc/' + UNIXuser
        VNC_SOCKET[display] = vnc_socket

        # Run some sanity checks on the files in /run/vnc to make sure
        # they're actually sockets and we can read them.

        vnc_socket_stat = os.stat(vnc_socket)
        if not stat.S_ISSOCK(vnc_socket_stat.st_mode):
            break

        if not os.access(vnc_socket, os.R_OK):
            break

        if (include_default_display and UNIXuser == myMeetingID) or \
           ((UNIXuser != myMeetingID) and (all_displays or UNIXuser in IDS.keys())):

            if all_displays or display not in LABELS:
                LABELS[display] = UNIXuser
            if display not in IDS:
                IDS[display] = ""

            # the default display is listed in /var/run under the meeting ID,
            # but is owned by the user 'default'

            if display == myMeetingID:
                UNIXUSER[display] = 'default'
            else:
                UNIXUSER[display] = UNIXuser

            VALID_DISPLAYS.append(display)

        # XXX this will hang if any of our VNC displays don't respond to the VNC protocol
        # XXX should we only do this for the displays we're working on (to optimize this)
        if display not in VNCdata:
            VNCdata[display] = get_VNC_info(VNC_SOCKET[display])

    # Having obtained a list of VNC sockets, we now wish to obtain
    # their X11 display names.
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
            X11_DISPLAY[display] = ':' + VNCdata[display]['name'].decode().split()[0].split(':')[1]
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

def main_loop_1():

    global processes
    global locations

    # query the properties on the root window (set by the window manager)
    # to see what display mode the user has selected.
    #
    # Would be more efficient to do this by leaving an "xprop -spy"
    # running in the background

    xprop = subprocess.Popen(["xprop", "-root"], stdout=subprocess.PIPE)
    (stdoutdata, stderrdata) = xprop.communicate()
    for l in stdoutdata.decode().split('\n'):
        if l.startswith('collaborate_display_mode'):
            global collaborate_display_mode
            collaborate_display_mode = l.split('"')[1]

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
            if display not in processes and display in VNCdata:
                # pick the first screen location not already claimed in locations
                i = [i for i in range(len(VALID_DISPLAYS)) if i not in locations.values()][0]
                locations[display] = i

                processes[display] = []
                row = int(i/cols)
                col = i%cols
                nativex = VNCdata[display]['width']
                nativey = VNCdata[display]['height']
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

                # The default user is special - use the label for BBB users that
                # mapped to no UNIX user
                if display == myMeetingID:
                    label = LABELS[None]
                else:
                    label = LABELS[display]
                processes[display].append(simple_text(label, geox + SCREENX/cols/2, geoy))

def main_loop():
    try:
        main_loop_1()
    except Exception as ex:
        simple_text(repr(ex), SCREENX/2, SCREENY - 300)

def restore_original_state():
    for procs in processes.values():
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

def teacher_desktop(screenx=None, screeny=None):

    get_global_display_geometry(screenx, screeny)

    if display_JWT:
        try:
            JWT = jwt.decode(os.environ['JWT'], verify=False)
            text = '\n'.join([str(k) + ": " + str(v) for k,v in JWT.items()])
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

#
# THE SCREENSHARE FEATURE
#

def close_projection_button():
    def app():

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

        # Implementing this function with the multiprocessing package
        # is problematic.  We inherit a lot of state from the parent
        # process, in particular, its signal handlers, which were
        # changed in teacher_desktop(), and I do depend on being able
        # to close this window by sending it SIGTERM.  Maybe it would
        # be best to spawn an entire new Python process to avoid these
        # kinds of problems, i.e, use process.Popen rather than
        # multiprocessing.Process.

        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        window.mainloop()

    process = multiprocessing.Process(target = app)
    process.start()
    return process

def project_to_one_display(display, display_to_project, processes):
    # We're projecting display_to_project (screenx/screeny) to the student screen (display/nativex/nativey)
    screenx = VNCdata[display_to_project]['width']
    screeny = VNCdata[display_to_project]['height']
    studentx = VNCdata[display]['width']
    studenty = VNCdata[display]['height']
    scalex = studentx/screenx
    scaley = studenty/screeny
    scale = min(scalex, scaley)
    offsetx = int((studentx - scale*screenx)/2)
    offsety = int((studenty - scale*screeny)/2)
    # This title is recognized by the FVWM config and is presented to the user
    # on top of all other windows and with no window manager decorations.
    title = "OverlayVNC"

    args = [VIEWONLY_VIEWER,
            '-viewonly', '-geometry', '+'+str(offsetx)+'+'+str(offsety),
            '-escape', 'never', '-display', X11_DISPLAY[display],
            '-scale', str(scale),
            '-title', title, 'unix=' + VNC_SOCKET[display_to_project]]

    # We should be in the 'bigbluebutton' group, and therefore able to read the student's
    # .Xauthority files to get the keys needed to put a window on their screen.
    # Not having this permission is a common enough error than I check for it here.

    XAUTHORITY = '/home/{}/.Xauthority'.format(UNIXUSER[display])
    if os.access(XAUTHORITY, os.R_OK):
        processes[display] = subprocess.Popen(args, stderr=subprocess.PIPE,
                                              env={'XAUTHORITY' : XAUTHORITY})
    else:
        processes[display] = simple_text("Can't read " + XAUTHORITY, SCREENX/2, SCREENY - 300)

def project_to_students_inner_function(student_window_name = None):
    r"""
    Project the teacher's desktop to all student desktops

    "Inner" function because it's wrapped in a try/except loop that catches
    exceptions and displays them using Tk widgets.
    """

    processes = dict()

    display_to_project = None

    if student_window_name:
        # see comment in teacher_zoom to understand this
        args = student_window_name.replace("\\'", "'")[1:-1].split(';')
        if len(args) >= 4 and args[0] == 'TeacherViewVNC':
            STUDENT_ID = args[1]
            STUDENT_DISPLAY = args[2]
            # NATIVE_GEOMETRY contains the geometry detected by the script that produced the grid view
            # We ignore it and query the geometry ourselves (in get_VALID_DISPLAYS)
            NATIVE_GEOMETRY = args[3]
            X_VNC_SOCKET = args[4]
            display_to_project = STUDENT_DISPLAY

    if not display_to_project:
        process = simple_text("Screenshare not called correctly", SCREENX/2, SCREENY - 300)
        time.sleep(5)
        kill_processes([process])
        return

    # Now put a window up on the teacher's screen to control the projection
    # and wait for it to close.

    process = close_projection_button()

    while True:
        # never screenshare to all displays; screenshare to current meeting only
        get_VALID_DISPLAYS(all_displays = False, include_default_display = True)

        for display in VALID_DISPLAYS:
            if display != display_to_project and display in X11_DISPLAY and display in VNCdata and display not in processes:
                project_to_one_display(display, display_to_project, processes)

        # if projection button has been closed, end the projection
        process.join(timeout=1)
        if not process.is_alive():
            break

        # If any of the screenshare processes die prematurely, show an
        # error message to the presenter.
        # XXX - multiple error messages will overlap

        for display,p in list(processes.items()):
            if isinstance(p, subprocess.Popen):
                p.poll()
                if p.returncode:
                    processes[display] = simple_text(p.stderr.read(), SCREENX/2, SCREENY - 300)
            elif isinstance(p, multiprocessing.Process):
                if not p.is_alive():
                    processes[display] = simple_text('process died', SCREENX/2, SCREENY - 300)

    # When the window closes, end the projection

    kill_processes(processes.values())

def project_to_students(screenx, screeny, student_window_name = None):
    get_global_display_geometry(screenx, screeny)

    try:
        project_to_students_inner_function(student_window_name)
    except Exception as ex:
        processes = []
        processes.append(simple_text(repr(ex), SCREENX/2, SCREENY - 300))
        time.sleep(5)
        kill_processes(processes)

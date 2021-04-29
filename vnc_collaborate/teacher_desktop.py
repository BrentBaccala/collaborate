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

import pymongo

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
#   - futures to acquire VNCdata asynchronously
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
VNCdata_futures = dict()

# myMeetingID: the Big Blue Button meeting identifier, which we fetch
# from the JSON Web Token passed in from websockify via the
# environment

myMeetingID = None

# screen geometry of the display used for the grid view
SCREENX = 0
SCREENY = 0

try:
    JWT = jwt.decode(os.environ['JWT'], verify=False)
    myMeetingID = JWT['bbb-meetingID']
except:
    pass

def get_VALID_DISPLAYS():
    r"""
    This function relies on the desktops having UNIX domain sockets in /run/vnc.
    """

    # query the properties on the root window (set by the window manager)
    # to see what display mode the user has selected.
    #
    # Default is to show all desktops running on the system.
    #
    # Would be more efficient to do this by leaving an "xprop -spy"
    # running in the background

    collaborate_display_mode = 'all'

    xprop = subprocess.Popen(["xprop", "-root"], stdout=subprocess.PIPE)
    (stdoutdata, stderrdata) = xprop.communicate()
    for l in stdoutdata.decode().split('\n'):
        if l.startswith('collaborate_display_mode'):
            collaborate_display_mode = l.split('"')[1]

    # If collaborate_display_mode is 'current_meeting' we limit the display to
    # only those users in the specified meeting.

    all_displays = (collaborate_display_mode == 'all')

    VALID_DISPLAYS.clear()
    LABELS.clear()
    IDS.clear()

    # Would be more efficient to do this using Big Blue Button webhooks
    # that by querying the API every time through this function.

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
    include_default_display = (collaborate_display_mode == 'current_meeting' and None in LABELS)

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

        # XXX should we only do this for the displays we're working on (to optimize this)
        if display not in VNCdata_futures:
            VNCdata_futures[display] = get_VNC_info(VNC_SOCKET[display], return_future=True)

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

    # Don't do this anymore here; wait until the VNCdata future has resolved
    #
    # for display in VALID_DISPLAYS:
    #     try:
    #         X11_DISPLAY[display] = ':' + VNCdata[display]['name'].decode().split()[0].split(':')[1]
    #     except:
    #         pass

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

# Current grid geometry

num_cols = 0
num_rows = 0

def calculate_grid_dimensions():
    r"""
    Calculate number of rows and columns in grid.

    Currently based on the screen geometry of the largest display in the grid.

    We pick a grid layout that maximizes the scaling of that largest display
    while also creating a grid large enough for all "valid" displays.

    Note: displays aren't fully "valid", and don't appear in the grid, unless
    we've also got screen geometry for them.  Without a response to the screen
    geometry query, they don't appear, even if they're in VALID_DISPLAYS.
    """
    max_width = 0
    max_height = 0
    num_displays = 0

    for display in VALID_DISPLAYS:
        # check to see if our query for display geometry finished, and if so, record the result
        if display in VNCdata_futures and display not in VNCdata:
            if VNCdata_futures[display].done():
                VNCdata[display] = VNCdata_futures[display].result()
                X11_DISPLAY[display] = ':' + VNCdata[display]['name'].decode().split()[0].split(':')[1]
        if display in VNCdata:
            max_width = max(max_width, int(VNCdata[display]['width']))
            max_height = max(max_height, int(VNCdata[display]['height']))
            num_displays += 1

    if num_displays == 0: return (0,0)

    rows = 1
    cols = 1

    # increase the number of rows and cols (separately) until the grid is big enough,
    # always trying to maximum the scaling factor

    while rows*cols < num_displays:
        NEXTGRIDX = int(SCREENX/(cols+1) - .01*SCREENX)
        NEXTGRIDY = int(SCREENY/(rows+1) - .01*SCREENY)
        nextscalex = NEXTGRIDX/max_width
        nextscaley = NEXTGRIDY/max_height

        if nextscalex < nextscaley:
            rows += 1
        else:
            cols += 1

    return (rows, cols)

def main_loop_grid(reset_display):
    r"""
    The portion of the main loop that draws the grid.
    """

    global processes
    global locations

    # If the number of clients changed enough to require a resize of
    # the entire display grid, kill all of our old processes,
    # triggering a rebuild of the entire display.

    # Otherwise, kill the processes for displays that are no longer
    # valid.  This is necessary to avoid a situation where we don't
    # have enough display slots available for the VALID_DISPLAYS,
    # which would trigger an exception a little later.

    if reset_display:
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

    if num_cols > 0 and num_rows > 0:

        # each pane has a .005 margin around it on all four sides
        # this produces a total gap of .01 between any two panes

        SCALEX = int(SCREENX/num_cols - .01*SCREENX)
        SCALEY = int(SCREENY/num_rows - .01*SCREENY)

        SCALE = str(SCALEX) + "x" + str(SCALEY)

        for display in VALID_DISPLAYS:
            if display in VNCdata_futures and display not in VNCdata:
                if VNCdata_futures[display].done():
                    VNCdata[display] = VNCdata_futures[display].result()
                    X11_DISPLAY[display] = ':' + VNCdata[display]['name'].decode().split()[0].split(':')[1]
            # if we haven't started a viewer for this display (display not in processes)
            # and we've got valid VNCdata for it, add it to the grid
            if display not in processes and display in VNCdata:
                # pick the first screen location not already claimed in locations
                i = [i for i in range(len(VALID_DISPLAYS)) if i not in locations.values()][0]
                locations[display] = i

                processes[display] = []
                row = int(i/num_cols)
                col = i%num_cols
                nativex = VNCdata[display]['width']
                nativey = VNCdata[display]['height']
                geometry = str(nativex) + 'x' + str(nativey)
                scalex = SCALEX/nativex
                scaley = SCALEY/nativey
                scale = min(scalex, scaley)
                geox = int(col * SCREENX/num_cols + .005*SCREENX)
                geoy = int(row * SCREENY/num_rows + .005*SCREENY)
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

                #print(args, file=sys.stderr)
                #sys.stderr.flush()

                # The default user is special - use the label for BBB users that
                # mapped to no UNIX user
                if display == myMeetingID:
                    label = LABELS[None]
                else:
                    label = LABELS[display]
                processes[display].append(simple_text(label, geox + SCREENX/num_cols/2, geoy))

def get_current_screenshare():
    global db_vnc
    mongo_doc = db_vnc.find_one({'screenshare': {'$exists': True}, 'meetingID': myMeetingID})
    if mongo_doc:
        return mongo_doc['screenshare']
    else:
        return None

current_screenshare = None
current_screenshare_window = None
current_screenshare_button = None

def main_loop_screenshare(reset_display):
    r"""
    The part of the main loop that outlines a screenshared desktop and presents
    an 'end screenshare' button
    """

    global current_screenshare
    global current_screenshare_window
    global current_screenshare_button

    new_screenshare = get_current_screenshare()
    if current_screenshare != new_screenshare or reset_display:
        if current_screenshare_window:
            current_screenshare_window.terminate()
            # commented out because I'm afraid of this deadlocking us
            #current_screenshare_window.wait()
            current_screenshare_window = None
        if new_screenshare in locations:
            location = locations[new_screenshare]
            row = int(location / num_cols)
            col = location % num_cols
            geox = int(col * SCREENX/num_cols)
            geoy = int(row * SCREENY/num_rows)
            SCALEX = int(SCREENX/num_cols)
            SCALEY = int(SCREENY/num_rows)

            current_screenshare_window = colored_rect(SCALEX, SCALEY, geox, geoy)
        current_screenshare = new_screenshare

    if current_screenshare and not current_screenshare_button:
        current_screenshare_button = close_projection_button()
    if not current_screenshare and current_screenshare_button:
        current_screenshare_button.terminate()
        current_screenshare_button = None
        # again, I'd like to wait for this, but am afraid to

def main_loop():
    try:
        geometry_changed = get_global_display_geometry()
        if geometry_changed:
            args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print teacher_mode_fvwm_config'", "-r"]
            global fvwm
            fvwm = subprocess.Popen(args)
            # we need to wait until the new fvwm has started before we layout windows on the screen,
            # or the vncviewers that go beyond the edges of the old screen geometry will get smashed
            # into the upper-left hand corner.  The Tk windows don't have this problem, who knows why.
            time.sleep(0.1)

        get_VALID_DISPLAYS()
        global num_rows, num_cols
        (old_rows, old_cols) = (num_rows, num_cols)
        (num_rows, num_cols) = calculate_grid_dimensions()
        grid_changed = ((old_rows, old_cols) != (num_rows, num_cols))
        main_loop_grid(geometry_changed or grid_changed)
        main_loop_screenshare(geometry_changed or grid_changed)

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

def get_global_display_geometry():
    r"""
    Get the display geometry of the "master" display and return True if
    that geometry changed since the last time this function was called.
    """

    global SCREENX, SCREENY

    (screenx, screeny) = subprocess.run(['xdotool', 'getdisplaygeometry'],
                                        stdout=subprocess.PIPE, encoding='ascii').stdout.split()
    if SCREENX != int(screenx) or SCREENY != int(screeny):
        SCREENX = int(screenx)
        SCREENY = int(screeny)
        #print("New screen geometry:",SCREENX,SCREENY,file=sys.stderr)
        #sys.stderr.flush()
        return True
    else:
        return False

def teacher_desktop(screenx=None, screeny=None):

    if display_JWT:
        try:
            JWT = jwt.decode(os.environ['JWT'], verify=False)
            text = '\n'.join([str(k) + ": " + str(v) for k,v in JWT.items()])
        except Exception as ex:
            text = repr(ex)
        simple_text(text, SCREENX/2, SCREENY - 100)

    # open the mongo database so we can watch for screenshare notifications

    global db_vnc
    client = pymongo.MongoClient('mongodb://127.0.1.1/')
    db = client.meteor
    db_vnc = db.vnc

    # When switching to teacher mode, we completely replace the FVWM window manager with a new
    # instance using a completely different config, then switch back to the original config
    # (using yet another new FVWM instance) when we're not.  Not ideal, but it works.

    args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print teacher_mode_fvwm_config'", "-r"]
    global fvwm
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

        # Once the window closes, probably from the FVWM window manager
        # (see comment there), end any active screen shares for this
        # meeting.

        client = pymongo.MongoClient('mongodb://127.0.1.1/')
        db = client.meteor
        db_vnc = db.vnc
        db_vnc.remove({'meetingID': myMeetingID})

    process = multiprocessing.Process(target = app)
    process.start()
    return process

def colored_rect(width, height, xlocation, ylocation):
    r"""
    Fork a subprocess to display a colored rectangle, using the tk toolkit.

    Returns a multiprocessing.Process object that manages the subprocess.
    """
    def app():

        window = tk.Tk()

        window.geometry(str(width)+"x"+str(height)+"+"+str(xlocation)+"+"+str(ylocation))
        window.configure(background = 'red')
        # setting window title 'highlight' causes FVWM to move this window below all others
        window.title('highlight')

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

def project_to_students(screenx, screeny, student_window_name = None):

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

    # put a screenshare announcement into mongo, which will trigger
    # both the actual screenshares on the student desktops and the
    # outline indicator and close button on the teacher desktops

    client = pymongo.MongoClient('mongodb://127.0.1.1/')
    db = client.meteor
    db_vnc = db.vnc
    db_vnc.insert({'screenshare': STUDENT_DISPLAY, 'meetingID': myMeetingID})

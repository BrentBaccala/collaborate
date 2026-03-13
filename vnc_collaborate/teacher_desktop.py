#
# Usage: teacher-desktop(MAX-DIMENSION, MIN-DIMENSION)
#
# This code displays the grid view.

import subprocess
import multiprocessing
import threading
import http.server

import sys
import math
import time
import psutil
import re
import signal
import os
import glob
import stat
import getpass
import grp

import tkinter as tk

from lxml import etree

import bigbluebutton

import psycopg2

from .simple_text import simple_text
from .vnc import get_VNC_info
from .users import fullName_to_UNIX_username, fullName_to_rfbport

def debug(*args, **kwargs):
    pass
    #kwargs['file'] = sys.stderr
    #kwargs['flush'] = True
    #print(*args, **kwargs)

def error(*args, **kwargs):
    kwargs['file'] = sys.stderr
    kwargs['flush'] = True
    print(*args, **kwargs)

# My user name.  Typically the UNIX user name of the user running the display in grid mode.

myUNIXname = getpass.getuser()

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
VNCdata = dict()
VNCdata_futures = dict()

# myMeetingID: the Big Blue Button meeting identifier

myMeetingID = os.environ.get('MeetingId')

# screen geometry of the display used for the grid view
SCREENX = 0
SCREENY = 0

# The PostgreSQL connection (None if not connected) for screenshare notifications
pg_conn = None

# get_xprop works for the string data type only
def get_xprop(name, default=None):
    xprop = subprocess.Popen(["xprop", "-root"], stdout=subprocess.PIPE)
    # communicate() waits for the subprocess to exit
    (stdoutdata, stderrdata) = xprop.communicate()
    for l in stdoutdata.decode().split('\n'):
        if l.startswith(name):
            debug('xprop', name, l.split('"')[1])
            return l.split('"')[1]
    debug('xprop', name, 'default', default)
    return default

def get_VALID_DISPLAYS():
    r"""
    This function relies on the desktops having UNIX domain sockets in /run/vnc.
    """

    # query the properties on the root window (set by the window manager)
    # to see what display mode the user has selected.
    #
    # Default is to show all desktops running on the system.
    #
    # Currently works by running xprop every time we query.
    # main_loop() is called once every second.
    #
    # Would be more efficient to do this by leaving an "xprop -spy"
    # running in the background

    collaborate_display_mode = get_xprop('collaborate_display_mode', default='all')

    # If collaborate_display_mode is 'current_meeting' we limit the display to
    # only those users in the specified meeting.

    all_displays = (collaborate_display_mode == 'all')

    VALID_DISPLAYS.clear()
    LABELS.clear()
    IDS.clear()

    # Would be more efficient to do this using Big Blue Button webhooks
    # that by querying the API every time through this function.

    if myMeetingID and not all_displays:
        # some kind of problem with this API call
        # meetingInfo = bigbluebutton.getMeetingInfo(meetingID = myMeetingID)
        meetingInfo = bigbluebutton.getMeetings().xpath('.//internalMeetingID[text()=$meetingID]/..', meetingID= myMeetingID)[0]
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
            continue

        if not os.access(vnc_socket, os.R_OK):
            continue

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

        # We now want to obtain VNC information, currently just width and height so we can figure what
        # scaling and geometry we need to put it in the grid.  get_VNC_info() used the vncdotool
        # package, which either waits for a response from the VNC server (return_future=False) or
        # returns a future without waiting (return_future=True).  We use the future version, so
        # the code can't hang here, and check later for the result.
        #
        # XXX should we only do this for the displays we're working on (to optimize this)

        if display not in VNCdata_futures:
            VNCdata_futures[display] = get_VNC_info(VNC_SOCKET[display], return_future=True)

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

# max_rows = 2
# max_cols = 2

page_number = 0

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
        if display in VNCdata:
            max_width = max(max_width, int(VNCdata[display]['width']))
            max_height = max(max_height, int(VNCdata[display]['height']))
            num_displays += 1

    if num_displays == 0: return (0,0)

    rows = 1
    cols = 1

    max_rows = int(get_xprop('max_rows', '5'))
    max_cols = int(get_xprop('max_cols', '5'))

    # increase the number of rows and cols (separately) until the grid is big enough,
    # always trying to maximum the scaling factor

    while rows*cols < num_displays:
        NEXTGRIDX = int(SCREENX/(cols+1) - .01*SCREENX)
        NEXTGRIDY = int(SCREENY/(rows+1) - .01*SCREENY)
        nextscalex = NEXTGRIDX/max_width
        nextscaley = NEXTGRIDY/max_height

        if (nextscalex < nextscaley) and (rows < max_rows):
            rows += 1
        elif cols < max_cols:
            cols += 1
        else:
            break

    return (rows, cols)

def move_window(name_regex, x, y):
    debug(["xdotool", "search", "--name", name_regex, "windowmove", str(x), str(y)], file=sys.stderr)
    subprocess.run(["xdotool", "search", "--name", name_regex, "windowmove", str(x), str(y)])

def main_loop_grid(reset_display):
    r"""
    The portion of the main loop that draws the grid.
    """

    debug("main_loop_grid", reset_display)

    global processes
    global locations

    # If the number of clients changed enough to require a resize of
    # the entire display grid, kill all of our old processes,
    # triggering a rebuild of the entire display.

    # Otherwise, kill the processes for displays that are no longer
    # valid.  This is necessary to avoid a situation where we don't
    # have enough display slots available for the VALID_DISPLAYS,
    # which would trigger an exception a little later.

    starting_location = page_number * num_rows * num_cols
    ending_location = starting_location + num_rows * num_cols - 1

    if reset_display:
        debug('killing all processes')
        for procs in processes.values():
            kill_processes(procs)
        processes.clear()
        locations.clear()
    else:
        DEAD_DISPLAYS = [disp for disp in processes.keys() if disp not in VALID_DISPLAYS]
        for disp in DEAD_DISPLAYS:
            debug('killing DEAD_DISPLAY', disp)
            kill_processes(processes[disp])
            processes.pop(disp)
            locations.pop(disp)

    delete_pkeys = []
    for pkey, plist in processes.items():
        for p in plist:
            # These lists contain both subprocess.Popen's and multiprocessing.Process's
            if isinstance(p, subprocess.Popen) and p.poll():
                # do something more than just log the error, but for now, just log the error
                error('display process died')
                (stdoutdata, stderrdata) = p.communicate()
                error(stdoutdata)
                error(stderrdata)
                delete_pkeys.append(pkey)

    for disp in delete_pkeys:
        kill_processes(processes[disp])
        processes.pop(disp)
        locations.pop(disp)

    if num_cols > 0 and num_rows > 0:

        # each pane has a .005 margin around it on all four sides
        # this produces a total gap of .01 between any two panes

        SCALEX = int(SCREENX/num_cols - .01*SCREENX)
        SCALEY = int(SCREENY/num_rows - .01*SCREENY)

        SCALE = str(SCALEX) + "x" + str(SCALEY)

        next_location = 0

        for display in sorted(VALID_DISPLAYS):
            # skip any displays that we don't have VNCdata for
            if display in VNCdata_futures and display not in VNCdata:
                if VNCdata_futures[display].done():
                    VNCdata[display] = VNCdata_futures[display].result()
            if display not in VNCdata:
                continue

            # we've got valid VNCdata (so it answers VNC requests and we know its geometry),
            # place it in the grid at next_location

            page = next_location // grid_size
            row = (next_location % grid_size) // num_cols
            col = next_location % num_cols
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

            if display in locations and locations[display] != next_location:
                # it moved in the grid
                if display in processes and page == page_number:
                    # it moved in the grid, and it's already being displayed, and it's on the current page,
                    # so just move it and its label (these are regular expressions matching the window name)
                    move_window(f';{display};', geox+offsetx, geoy+offsety)
                    move_window(f'^{display}$', geox+SCREENX/num_cols/2, geoy)

            if display in processes and page != page_number:
                # it moved off the page
                debug('killing off screen display', display)
                kill_processes(processes[display])
                processes.pop(display)

            if display not in processes and page == page_number:
                # we haven't started a viewer for this display, but we should
                processes[display] = []
                args = [VIEWONLY_VIEWER, '-viewonly', '-geometry', '+'+str(geox+offsetx)+'+'+str(geoy+offsety),
                        '-escape', 'never',
                        '-scale', str(scale),
                        '-title', title, 'unix=' + VNC_SOCKET[display]]
                processes[display].append(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE))

                # Put a label on the window.  The default user is special - use the label for BBB users that
                # mapped to no UNIX user

                if display == myMeetingID:
                    label = LABELS[None]
                else:
                    label = LABELS[display]
                processes[display].append(simple_text(label, geox + SCREENX/num_cols/2, geoy))

            locations[display] = next_location
            next_location += 1

def get_current_screenshare():
    if pg_conn:
        try:
            cur = pg_conn.cursor()
            cur.execute('SELECT screenshare FROM vnc_screenshare WHERE "meetingId" = %s', (myMeetingID,))
            row = cur.fetchone()
            cur.close()
            if row:
                return row[0]
        except psycopg2.Error:
            pass
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

    global page_number, grid_size

    new_screenshare = get_current_screenshare()
    if current_screenshare != new_screenshare or reset_display:
        if current_screenshare_window:
            current_screenshare_window.terminate()
            # commented out because I'm afraid of this deadlocking us
            #current_screenshare_window.wait()
            current_screenshare_window = None
        if new_screenshare in locations and (locations[new_screenshare] // grid_size) == page_number:
            location = locations[new_screenshare] % grid_size
            row = location // num_cols
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
        # If the geometry of the grid view changed (user selected "Set Geometry" from menu), we need to restart fvwm
        geometry_changed = get_global_display_geometry()
        if geometry_changed:
            fvwm_config = 'teacher_mode_fvwm_config'
            args = ["fvwm", "-c", "PipeRead 'python3 -m vnc_collaborate print %s'" % fvwm_config, "-r"]
            global fvwm
            fvwm = subprocess.Popen(args)
            # we need to wait until the new fvwm has started before we layout windows on the screen,
            # or the vncviewers that go beyond the edges of the old screen geometry will get smashed
            # into the upper-left hand corner, along with the "end screenshare" button.
            # The Tk labels on the desktops don't have this problem, who knows why.
            time.sleep(0.1)

        get_VALID_DISPLAYS()
        debug('VALID_DISPLAYS', VALID_DISPLAYS)

        global num_rows, num_cols, grid_size
        (old_rows, old_cols) = (num_rows, num_cols)
        (num_rows, num_cols) = calculate_grid_dimensions()
        grid_changed = ((old_rows, old_cols) != (num_rows, num_cols))
        grid_size = num_rows * num_cols

        global page_number
        old_page_number = page_number
        page_number = int(get_xprop('page_number', '0'))
        page_changed = (old_page_number != page_number)

        # we don't need to pass page_changed to main_loop_grid, because it will already kill all off-screen viewers
        main_loop_grid(geometry_changed or grid_changed)
        main_loop_screenshare(geometry_changed or grid_changed or page_changed)

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

    This would typically happen because the user clicked on the Set Geometry
    option from the pull-down menu in grid mode, and that runs xrandr.
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

def open_pg_database():
    global pg_conn
    try:
        pg_conn = psycopg2.connect(host='127.0.0.1', dbname='collaborate',
                                   user='collaborate', password='collaborate')
        pg_conn.autocommit = True
    except psycopg2.Error:
        pg_conn = None

def launch_desktop_viewer():
    r"""
    Launch a zoomed VNC viewer of the moderator's own desktop on desktop 0.
    Returns True if the viewer was launched, False if it couldn't be.
    """
    vnc_socket = '/run/vnc/' + myUNIXname
    if not os.path.exists(vnc_socket):
        return False

    # Get the moderator's desktop geometry
    if myUNIXname in VNCdata:
        nativex = VNCdata[myUNIXname]['width']
        nativey = VNCdata[myUNIXname]['height']
    else:
        nativex = SCREENX
        nativey = SCREENY

    geometry = str(nativex) + 'x' + str(nativey)
    # Build a window name matching the TeacherViewVNC pattern so
    # FVWM's DestroyWindowEvent handler recognizes it
    window_name = ";".join(["TeacherViewVNC", "", myUNIXname, geometry, vnc_socket])

    # Launch teacher_zoom the same way FVWM's ZoomDesktop does
    subprocess.Popen([
        "python3", "-m", "vnc_collaborate", "teacher_zoom",
        "'" + window_name + "'",
        str(SCREENX), str(SCREENY),
    ])

    # Wait for the TigerVNC viewer window to appear on desktop 0
    for _ in range(50):  # up to 5 seconds
        result = subprocess.run(
            ["xdotool", "search", "--desktop", "0", "--name", "TigerVNC"],
            stdout=subprocess.PIPE, encoding='ascii'
        )
        if result.stdout.strip():
            break
        time.sleep(0.1)

    return True

def toggle_desktop_view():
    r"""
    Toggle between the moderator's own desktop and grid mode.

    Desktop 0 is the moderator's desktop (zoomed view).
    Desktop 1 is the grid view showing student desktops.

    If on desktop 0 (desktop view): switch to grid view on desktop 1.
    If on desktop 1 (grid view): launch a zoomed VNC viewer of the
    moderator's own desktop on desktop 0 and switch there.
    """
    current_desk = subprocess.run(
        ["xdotool", "get_desktop"],
        stdout=subprocess.PIPE, encoding='ascii'
    ).stdout.strip()

    if current_desk == '1':
        # We're in grid mode — zoom to the moderator's own desktop
        if not launch_desktop_viewer():
            return

        # Switch to desktop 0 (where zoomed views live)
        subprocess.run(["xdotool", "set_desktop", "0"])
        # Tell FVWM to remove grid bindings (F24)
        subprocess.run(["xdotool", "key", "F24"])

    else:
        # We're on the desktop view — kill zoomed viewer windows.
        # Search on desktop 0 only to avoid killing grid viewers on desktop 1.
        for pattern in ["Zoomed Student Desktop", "TigerVNC"]:
            result = subprocess.run(
                ["xdotool", "search", "--desktop", "0", "--name", pattern],
                stdout=subprocess.PIPE, encoding='ascii'
            )
            for wid in result.stdout.strip().split('\n'):
                if wid:
                    subprocess.run(["xdotool", "windowclose", wid])
        # Switch to desktop 1 (grid view).
        time.sleep(0.5)
        subprocess.run(["xdotool", "set_desktop", "1"])
        # Tell FVWM to restore grid bindings (F23)
        subprocess.run(["xdotool", "key", "F23"])

class TeacherDesktopHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/grid-toggle':
            toggle_desktop_view()
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def start_http_listener():
    r"""
    Start a lightweight HTTP server on a random port, bound to localhost only.
    Sets TEACHER_DESKTOP_PORT in the environment so FVWM key bindings can
    use it to curl the appropriate endpoint.
    """
    server = http.server.HTTPServer(('127.0.0.1', 0), TeacherDesktopHandler)
    port = server.server_address[1]
    os.environ['TEACHER_DESKTOP_PORT'] = str(port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

def teacher_desktop(screenx=None, screeny=None):

    # Start HTTP listener for plugin commands (grid toggle, etc.)
    # Must start before FVWM so $TEACHER_DESKTOP_PORT is available in the environment
    start_http_listener()

    # Map F13-F24 keysyms to keycodes so that FVWM can bind to them.
    # The TigerVNC X server's default keymap only includes F1-F12.
    # These keys are used by the BBB remote desktop plugin to send commands
    # via noVNC's sendKey() — the VNC server needs keycode mappings to
    # generate X11 KeyPress events from the received keysyms.
    # We use unused keycodes and some rarely-needed multimedia keycodes.
    unused_keycodes = [8, 93, 97, 103, 120, 132, 149, 154, 168, 178, 183, 184]
    for i, keycode in enumerate(unused_keycodes):
        subprocess.run(["xmodmap", "-e", f"keycode {keycode} = F{13 + i}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # open the PostgreSQL database in background so it doesn't hang us if the database doesn't exist
    thread = threading.Thread(target=open_pg_database)
    thread.start()
    # at some point, should do thread.join()

    # I've seen a race condition where the xsetroot, and the fvwm that follows in main_loop(),
    # errors out, unable to open the display.  So retry the xsetroot until it succeeds.
    retry_attempts = 10
    while subprocess.run(["xsetroot", "-solid", "black"]).returncode != 0 and retry_attempts > 0:
        retry_attempts -= 1
    debug('initial call to main_loop')
    main_loop()

    # FVWM starts on desktop 0 (desktop view).  main_loop() creates
    # grid windows on desktop 1, which may cause FVWM to switch there
    # despite SkipMapping.  Ensure we're on desktop 0 and launch the
    # moderator's own desktop viewer so desk 0 isn't a black screen.
    subprocess.run(["xdotool", "set_desktop", "0"])
    launch_desktop_viewer()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Big Blue Button currently (version 2.2.22) lacks a mechanism in its REST API
    # to get notifications when users come and go.  So we poll every second to
    # update the display until FVWM exits.

    while True:
        try:
            fvwm.wait(timeout=1)
            debug('fvwm exited')
            break
        except subprocess.TimeoutExpired:
            debug('fvwm.wait TimeoutExpired')
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

        try:
            conn = psycopg2.connect(host='127.0.0.1', dbname='collaborate',
                                    user='collaborate', password='collaborate')
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute('DELETE FROM vnc_screenshare WHERE "meetingId" = %s', (myMeetingID,))
            cur.execute("NOTIFY vnc_screenshare")
            cur.close()
            conn.close()
        except psycopg2.Error:
            pass

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

    # put a screenshare announcement into PostgreSQL, which will trigger
    # both the actual screenshares on the student desktops and the
    # outline indicator and close button on the teacher desktops

    try:
        conn = psycopg2.connect(host='127.0.0.1', dbname='collaborate',
                                user='collaborate', password='collaborate')
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute('INSERT INTO vnc_screenshare ("meetingId", screenshare) VALUES (%s, %s) '
                    'ON CONFLICT ("meetingId") DO UPDATE SET screenshare = %s',
                    (myMeetingID, STUDENT_DISPLAY, STUDENT_DISPLAY))
        cur.execute("NOTIFY vnc_screenshare")
        cur.close()
        conn.close()
    except psycopg2.Error:
        pass

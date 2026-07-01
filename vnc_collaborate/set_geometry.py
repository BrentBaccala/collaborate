"""
set_geometry — change the resolution of the VNC desktop via RANDR.

Used by the "Set Geometry" pull-down in the teacher-mode and student-grid
FVWM menus.  Replaces the old menu command

    xrandr --fb WxH --output VNC-0 --off

which resized the framebuffer but then turned the sole output OFF.  Under a
RANDR-managing window manager (GNOME/mutter) the output gets re-enabled
automatically, so the old command appeared to work.  Under FVWM (the teacher
grid and student grid) nothing ever re-enables it, so the desktop goes black
and stays black.  It only ever "worked" because focal's TigerVNC 1.10
presented the framebuffer regardless of output state; jammy's TigerVNC 1.12
does not, so a disabled output is genuinely blank.

The correct approach is to leave the output enabled and point it at a mode of
the requested size:

    xrandr --fb WxH --output VNC-0 --mode <mode>

The wrinkle is that arbitrary sizes (1600x900, 3840x2160, ...) are not among
TigerVNC's built-in preset modes, so a matching mode has to be created first.
This module does that idempotently: it will not create a duplicate mode on
repeated calls with the same geometry, and it emits no spurious X errors.
"""

import re
import subprocess
import sys

OUTPUT = 'VNC-0'


def _xrandr(*args):
    """Run xrandr, capturing output; never raises."""
    return subprocess.run(['xrandr', *args],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding='ascii')


def _modeline_timing(width, height):
    """
    Return the RANDR modeline timing fields (everything after the name) for a
    WxH mode.  Prefer cvt; fall back to a trivially-valid synthetic modeline
    if cvt is unavailable.  For a virtual VNC output the exact timings are
    irrelevant — there is no real pixel clock — so any well-formed modeline
    with the correct active-pixel counts works.
    """
    try:
        cvt = subprocess.run(['cvt', str(width), str(height)],
                             stdout=subprocess.PIPE, encoding='ascii')
        m = re.search(r'Modeline\s+"[^"]*"\s+(.*)', cvt.stdout)
        if m:
            return m.group(1).split()
    except FileNotFoundError:
        pass

    # Fallback: a minimal modeline that satisfies RANDR's ordering
    # constraints (hdisp < hsync_start < hsync_end < htotal, likewise
    # vertically).  Nominal 60 Hz pixel clock; value is cosmetic here.
    clock = round(width * height * 60 / 1_000_000, 2)
    return [str(clock),
            str(width), str(width + 48), str(width + 96), str(width + 160),
            str(height), str(height + 3), str(height + 8), str(height + 40),
            '-hsync', '+vsync']


def _ensure_mode(width, height, output=OUTPUT):
    """
    Ensure a mode named "WxH" is attached to `output`, creating it if needed.
    Returns the mode name, or None on failure.

    Idempotent: --addmode of an already-attached mode succeeds (exit 0), so we
    try it first and only fall back to creating the mode when it is genuinely
    absent from the server's mode pool ("cannot find mode").  This avoids both
    duplicate modes and the BadName errors that repeated --newmode calls would
    otherwise produce.
    """
    name = '%dx%d' % (width, height)

    # Fast path: mode already known to the server (a TigerVNC preset, or one
    # we created earlier).  addmode is idempotent for already-attached modes.
    if _xrandr('--addmode', output, name).returncode == 0:
        return name

    # Mode absent from the pool: create it, then attach.
    _xrandr('--newmode', name, *_modeline_timing(width, height))
    add = _xrandr('--addmode', output, name)
    if add.returncode != 0:
        sys.stderr.write(add.stderr)
        return None
    return name


def set_geometry(geometry, output=OUTPUT):
    """
    Resize the VNC desktop to `geometry` (a "WxH" string), keeping the output
    enabled.  Returns a process-style exit code (0 = success).
    """
    m = re.fullmatch(r'(\d+)x(\d+)', geometry.strip())
    if not m:
        sys.stderr.write('set_geometry: invalid geometry %r (expected WxH)\n'
                         % geometry)
        return 1
    width, height = int(m.group(1)), int(m.group(2))

    name = _ensure_mode(width, height, output)
    if name is None:
        return 1

    result = _xrandr('--fb', '%dx%d' % (width, height),
                     '--output', output, '--mode', name)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
    return result.returncode

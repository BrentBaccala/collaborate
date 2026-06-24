
import subprocess


def set_vnc_desktop_name(name, display=None):
    """Set the RFB desktop name of the running Xtigervnc session.

    Uses the VncExt SetParam request (``vncconfig -set desktop=...``).  On
    Xtigervnc this changes the ``desktop`` parameter and immediately pushes an
    RFB DesktopName update to every connected client.  The BBB remote-desktop
    plugin listens for that update (noVNC ``desktopname`` event) and, when its
    ``showDesktopName`` setting is enabled, shows the name under this user in
    the moderator's user list -- i.e. which desktop the user is currently
    viewing.

    An empty ``name`` clears the label (the convention for "on my own
    desktop").  ``display`` defaults to ``$DISPLAY`` (the session these grid
    scripts run inside).

    Best-effort: this must never raise, since a vncconfig hiccup must not
    disrupt the grid/zoom flow.
    """
    # Collapse to a single clean line; ';' is stripped because the grid window
    # titles are ';'-delimited and a name carrying one would corrupt parsing.
    clean = " ".join(str(name).replace(";", " ").split())
    cmd = ["vncconfig"]
    if display:
        cmd += ["-display", display]
    cmd += ["-set", f"desktop={clean}"]
    try:
        subprocess.run(cmd, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

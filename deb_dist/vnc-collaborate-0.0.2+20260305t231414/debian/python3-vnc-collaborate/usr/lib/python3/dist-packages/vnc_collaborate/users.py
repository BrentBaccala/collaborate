# How do we map from Big Blue Button user names to UNIX usernames?
# (and/or the port number of that user's VNC/RFB server)
#
# This method is very simple - squash spaces and don't connect to
# any VNC servers other than the standard X11 desktops.
#
# There's an alternate, unused method in sqlusers.py.

def fullName_to_UNIX_username(fullName):
    return fullName.replace(' ', '')

def fullName_to_rfbport(fullName):
    return None

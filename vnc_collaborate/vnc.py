#
# Use the "twisted" RFB protocol implementation in the vncdotool
# package to query a VNC desktop for its name and geometry.
#
# The whole twisted package is a bit... twisted.  It's a
# single-threaded implementation and its main event loop can't be
# called twice, so we pass in a list of RFB ports that we
# want to query and get a dictionary returned back to us.
#
# An attempt to call get_VNC_info() a second time will throw
# an exception.

from vncdotool import rfb
from twisted.internet import reactor, protocol
from twisted.application import internet

ntargets = 0
VNC_data = {}

class RFBDataClient(rfb.RFBClient):
    def vncConnectionMade(self):
        global ntargets
        VNC_data[self.transport.addr[1]] = {
            'name': self.name,
            'width': self.width,
            'height': self.height
        }
        ntargets = ntargets - 1
        if ntargets == 0:
            reactor.stop()

class RFBFactory(protocol.ClientFactory):
    """A factory for remote frame buffer connections."""

    protocol = RFBDataClient

    # shared = 1 because we don't want to kick out
    # our users just to query their desktops

    def __init__(self, password = None, shared = 1):
        self.password = password
        self.shared = shared

def get_VNC_info(portlist):
    global ntargets
    for port in portlist:
        vncClient = internet.TCPClient('localhost', port, RFBFactory())
        vncClient.startService()
        ntargets = ntargets + 1
    reactor.run()
    return VNC_data

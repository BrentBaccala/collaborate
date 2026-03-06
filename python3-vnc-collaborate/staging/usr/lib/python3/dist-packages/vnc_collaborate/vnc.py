#
# Use the "twisted" RFB protocol implementation in the vncdotool
# package to query a VNC desktop for its name and geometry.
#
# The whole twisted package is a bit... twisted.  It's a
# single-threaded implementation and its main event loop can't be
# called twice, so we run in a different subprocess every time
# we call get_VNC_info().

from vncdotool import rfb
from twisted.internet import reactor, protocol
from twisted.application import internet
import concurrent.futures

VNC_data = None

class RFBDataClient(rfb.RFBClient):
    def vncConnectionMade(self):
        if type(self.transport.addr) == bytes:
            key = self.transport.addr.decode()   # UNIX socket case; decode() to use string, not bytes, as key
        else:
            key = self.transport.addr[1]         # TCP socket case

        global VNC_data
        VNC_data = {
            'name': self.name,
            'width': self.width,
            'height': self.height
        }
        reactor.stop()

class RFBFactory(protocol.ClientFactory):
    """A factory for remote frame buffer connections."""

    protocol = RFBDataClient

    # shared = 1 because we don't want to kick out
    # our users just to query their desktops

    def __init__(self, password = None, shared = 1):
        self.password = password
        self.shared = shared

def get_VNC_info_subprocess(port):
    if type(port) == int:
        vncClient = internet.TCPClient('localhost', port, RFBFactory())
    else:
        vncClient = internet.UNIXClient(port, RFBFactory())
    vncClient.startService()
    reactor.run()
    return VNC_data

def get_VNC_info(port, return_future=False):
    executor = concurrent.futures.ProcessPoolExecutor()
    future = executor.submit(get_VNC_info_subprocess, port)
    if return_future:
        return future
    else:
        return future.result()

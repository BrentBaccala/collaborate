"""
rfb_reject — speak just enough of the RFB (VNC) handshake to reject a client
with a human-readable *reason* string, then close.

This is the server-side half of the remote-desktop plugin's connection-error
overlay.  The plugin already renders the reason carried by noVNC's
``securityfailure`` event (``e.detail.reason``); the trouble is that a normal
collaborate rejection is an nginx HTTP 401 on ``/vnc`` *before* any RFB runs,
so the browser only ever sees a generic WebSocket close (1006) with no message.
To get a *specific* message to the user (e.g. "your session expired") the
rejection has to happen at the RFB layer instead, so noVNC fires
``securityfailure`` with our reason.

This module is an ``inetd``-style filter: it reads the client side of the
connection from stdin and writes the server side to stdout (websockify bridges
the WebSocket to it via ``socat UNIX-LISTEN ... EXEC:``, exactly like the real
VNC servers).  The reason comes from ``argv[1]`` or the ``RFB_REJECT_REASON``
environment variable.

RFB 3.8 handshake, minimal reject path (see RFC 6143 §7 and noVNC rfb.js
``_negotiateSecurity`` / ``_handleSecurityReason``):

    S->C  "RFB 003.008\n"                 (12 bytes, ProtocolVersion)
    C->S  "RFB 003.00x\n"                 (12 bytes, client's chosen version)
    S->C  0x00                            (number-of-security-types = 0 => failure)
    S->C  uint32 reason-length, reason    (the reason string, big-endian length)

When ``number-of-security-types`` is 0, a >=3.7 client enters its
"SecurityReason" state and reads the length-prefixed reason, then dispatches
``securityfailure`` with ``{status: 1, reason}``.  No security type is offered
and no SecurityResult is sent, so this is the shortest exchange that carries a
reason.
"""

import os
import sys
import struct


def _read_exactly(stream, n):
    """Read exactly n bytes (or fewer on EOF) from a binary stream."""
    buf = b''
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def rfb_reject(*args):
    reason = args[0] if args else os.environ.get('RFB_REJECT_REASON', '')
    if not reason:
        reason = 'The remote desktop connection was rejected.'

    out = sys.stdout.buffer
    inp = sys.stdin.buffer

    # 1. ProtocolVersion, server -> client
    out.write(b'RFB 003.008\n')
    out.flush()

    # 2. ProtocolVersion, client -> server (12 bytes); tolerate a short read
    #    (the client may hang up early — we just proceed to send the reason).
    _read_exactly(inp, 12)

    # 3. number-of-security-types = 0  -> the client treats this as a failure
    #    and reads a reason string next.
    out.write(b'\x00')

    # 4. reason: uint32 big-endian length, then the UTF-8 bytes
    reason_bytes = reason.encode('utf-8')
    out.write(struct.pack('>I', len(reason_bytes)))
    out.write(reason_bytes)
    out.flush()

    return 0

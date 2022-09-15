"""bigbluebutton - interface with a Big Blue Button videoconferencing system

The API functions defined in https://docs.bigbluebutton.org/dev/api.html
are supported.

Generally, read access to the API key in bigbluebutton.PROP_FILE is
required for all operations.

Examples:

    >>> import bigbluebutton
    >>> bigbluebutton.getMeetings()

    Only keyword arguments are supported, even if only a single
    argument is required.

    >>> bigbluebutton.getMeetingInfo(meetingID = 'max')

    To join a meeting, you often want to specify redirect=False to
    obtain an XML result with the URL, instead of an HTML result.

    >>> join_result = bigbluebutton.join(meetingID='osito',
                                         fullName='Charlie Clown',
                                         password='pw',
                                         redirect=False)
    >>> join_result.xpath('.//url')[0].text

Author: Brent Baccala <cosine@freesoft.org>
License: GNU Lesser General Public License

"""

import pyjavaproperties
import hashlib
import requests
import urllib

from lxml import etree

# We extract the Big Blue Button API key from PROP_FILE

BBB_WEB_CONFIG = "/usr/share/bbb-web/WEB-INF/classes/bigbluebutton.properties"
BBB_WEB_ETC_CONFIG="/etc/bigbluebutton/bbb-web.properties"

def properties():
    if not hasattr(properties, 'retval'):
        properties.retval = pyjavaproperties.Properties()
        for filename in [BBB_WEB_CONFIG, BBB_WEB_ETC_CONFIG]:
            with open(filename) as file:
                properties.retval.load(file)
    return properties.retval

def securitySalt():
    return properties()['securitySalt']

def serverURL():
    return properties()['bigbluebutton.web.serverURL']

def _APIurl(call_name, query_dict):
    r"""
    Construct the URL to make a Big Blue Button REST API call.  The
    first argument is the name of the API call; the second argument is
    a dictionary of parameters.

    Expect a string in return.
    """
    bbbUrl = serverURL() + '/bigbluebutton/api/'
    query_string = urllib.parse.urlencode(query_dict)
    checksum = hashlib.sha256((call_name + query_string + securitySalt()).encode('utf-8')).hexdigest()
    url = bbbUrl + call_name + '?' + query_string + '&checksum=' + checksum
    return url

def _APIcall(call_name, query_dict):
    r"""
    Make a Big Blue Button REST API call.  The first argument is the name
    of the API call; the second argument is a dictionary of parameters.

    Expect an etree XML object in return.
    """
    url = _APIurl(call_name, query_dict)
    response = requests.get(url)
    try:
        xml = etree.fromstring(response.text)
    except:
        return response.text
    return xml

def create(**kwargs):
    return _APIcall("create", kwargs)

def join(**kwargs):
    return _APIcall("join", kwargs)

def isMeetingRunning(**kwargs):
    return _APIcall("isMeetingRunning", kwargs)

def end(**kwargs):
    return _APIcall("end", kwargs)

def getMeetingInfo(**kwargs):
    return _APIcall("getMeetingInfo", kwargs)

def getMeetings():
    return _APIcall('getMeetings', {})

def publishRecordings(**kwargs):
    return _APIcall("publishRecordings", kwargs)

def deleteRecordings(**kwargs):
    return _APIcall("deleteRecordings", kwargs)

def updateRecordings(**kwargs):
    return _APIcall("updateRecordings", kwargs)

def getDefaultConfigXML():
    return _APIcall('getDefaultConfigXML', {})

def setConfigXML(**kwargs):
    return _APIcall("setConfigXML", kwargs)

def getRecordingTextTracks(**kwargs):
    return _APIcall("getRecordingTextTracks", kwargs)

def putRecordingTextTrack(**kwargs):
    return _APIcall("putRecordingTextTrack", kwargs)


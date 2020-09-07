
import pyjavaproperties
import hashlib
import requests

from lxml import etree

PROP_FILE = "/usr/share/bbb-web/WEB-INF/classes/bigbluebutton.properties"

def load_config():
    global config
    config = pyjavaproperties.Properties()
    with open(PROP_FILE) as file:
        config.load(file)

def getMeetingInfo(room_name):
    load_config()
    securitySalt = config['securitySalt']
    bbbUrl = config['bigbluebutton.web.serverURL'] + '/bigbluebutton/api/'
    call_name = 'getMeetingInfo'
    query = 'meetingID=' + room_name
    checksum = hashlib.sha256((call_name + query + securitySalt).encode('utf-8')).hexdigest()
    url = bbbUrl + call_name + '?' + query + '&checksum=' + checksum

    response = requests.get(url)
    xml = etree.fromstring(response.text)
    return xml


#        fullName = xml.xpath("string(.//userID[text()='{}']/../fullName)".format(userID))


import pyjavaproperties
import hashlib
import requests
import urllib
import os

from lxml import etree

import psycopg2

# We extract the Big Blue Button API key from PROP_FILE

PROP_FILE = "/usr/share/bbb-web/WEB-INF/classes/bigbluebutton.properties"

# We store mappings between BBB fullNames and UNIX usernames in a SQL table:
#
# CREATE TABLE VNCusers(VNCuser text, UNIXuser text, PRIMARY KEY (VNCuser))
#
# No password needed to connect to localhost when Postgres is configured for "trust" authentication.

postgreshost = 'localhost'
postgresdb = 'greenlight_production'
postgresuser = 'postgres'
postgrespw = None

config = None

def load_config():
    global config
    if not config:
        config = pyjavaproperties.Properties()
        with open(PROP_FILE) as file:
            config.load(file)

conn = None

def open_database():
    global conn
    if not conn:
        conn = psycopg2.connect(database=postgresdb, host=postgreshost, user=postgresuser, password=postgrespw)

def APIcall(call_name, query_dict):
    load_config()
    securitySalt = config['securitySalt']
    bbbUrl = config['bigbluebutton.web.serverURL'] + '/bigbluebutton/api/'
    query_string = urllib.parse.urlencode(query_dict)
    checksum = hashlib.sha256((call_name + query_string + securitySalt).encode('utf-8')).hexdigest()
    url = bbbUrl + call_name + '?' + query_string + '&checksum=' + checksum
    response = requests.get(url)
    xml = etree.fromstring(response.text)
    return xml

def getMeetings():
    return APIcall('getMeetings', {})

def getMeetingInfo(meetingID):
    return APIcall("getMeetingInfo", locals())

def find_current_meeting():
    # Lookup the current UNIX user in the VNCusers SQL table to pull
    # out the matching VNCuser (the BBB fullName).  Then look through
    # all the meetings on the BBB server to find the (first) one
    # where this user is a participant.
    #
    # XXX what should we do if the user is a participant in multiple meetings?

    username = os.environ['USER']
    myFullName = None
    open_database()
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT VNCuser FROM VNCusers WHERE UNIXuser = %s", (username,))
            row = cur.fetchone()
            if row:
                myFullName = row[0]
        except psycopg2.DatabaseError as err:
            print(err)
            cur.execute('ROLLBACK')

    if myFullName:
        meetings = getMeetings()
        for e in meetings.xpath(".//running[text()='true']/../meetingID"):
            meetingID = e.text
            meetingInfo = getMeetingInfo(meetingID)
            # I could query for just the fullName's that match myFullName,
            # but then I'd have to escape myFullName, and it just
            # seems like too much trouble at the moment.
            for ee in meetingInfo.xpath(".//fullName"):
                if ee.text == myFullName:
                    return meetingID

    return None

def fullName_to_UNIX_username(fullName):
    open_database()
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT UNIXuser FROM VNCusers WHERE VNCuser = %s", (fullName,))
            row = cur.fetchone()
            if row:
                return row[0]
        except psycopg2.DatabaseError as err:
            print(err)
            cur.execute('ROLLBACK')
    return None

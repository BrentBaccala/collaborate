
import pyjavaproperties
import hashlib
import requests
import urllib
import os

from lxml import etree

import psycopg2

# We extract the Big Blue Button API key from PROP_FILE

PROP_FILE = "/usr/share/bbb-web/WEB-INF/classes/bigbluebutton.properties"

# We use a SQL table to map from BBB fullNames to the UNIX usernames or RFB ports they connect to:
#
# CREATE TABLE VNCusers(VNCuser text NOT NULL, UNIXuser text, rfbport integer, PRIMARY KEY (VNCuser));
#
# We access the database using some hard-wired parameters.  Create the
# 'vnc' user with something like this:
#
# CREATE ROLE vnc LOGIN PASSWORD 'vnc';
#
# GRANT SELECT ON VNCusers to vnc;

postgreshost = 'localhost'
postgresdb = 'greenlight_production'
postgresuser = 'vnc'
postgrespw = 'vnc'

config = None

def load_config():
    global config
    if not config:
        config = pyjavaproperties.Properties()
        with open(PROP_FILE) as file:
            config.load(file)

def securitySalt():
    load_config()
    return config['securitySalt']

conn = None

def open_database():
    global conn
    if not conn:
        try:
            conn = psycopg2.connect(database=postgresdb, host=postgreshost, user=postgresuser, password=postgrespw)
        except psycopg2.DatabaseError as err:
            print(err)

def APIcall(call_name, query_dict):
    r"""
    Make a Big Blue Button REST API call.  The first argument is the name
    of the API call; the second argument is a dictionary of parameters.

    Expect an etree XML object in return.
    """
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

def fullName_to_UNIX_username(fullName):
    r"""
    Use a SQL table lookup to convert a Big Blue Button fullName
    into a UNIX username.
    """
    open_database()
    if conn:
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

def fullName_to_rfbport(fullName):
    r"""
    Use a SQL table lookup to convert a Big Blue Button fullName
    into a UNIX username.
    """
    open_database()
    if conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT rfbport FROM VNCusers WHERE VNCuser = %s", (fullName,))
                row = cur.fetchone()
                if row:
                    return row[0]
            except psycopg2.DatabaseError as err:
                print(err)
                cur.execute('ROLLBACK')
    return None

def UNIX_username_to_fullName(UNIXname):
    r"""
    Use a SQL table lookup to convert a UNIX username
    to a Big Blue Button fullName
    """
    open_database()
    if conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT VNCuser FROM VNCusers WHERE UNIXuser = %s", (UNIXname,))
                row = cur.fetchone()
                if row:
                    return row[0]
            except psycopg2.DatabaseError as err:
                print(err)
                cur.execute('ROLLBACK')
    return None

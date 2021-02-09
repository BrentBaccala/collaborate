#!/usr/bin/python3
#
# Read the current contents of Big Blue Button's "Shared Notes" and print
# it to stdout in either text or HTML format.
#
# I've figured how to map from a Big Blue Button meeting to the Shared
# Notes padID, but I'm still wrestling with how to figure how the
# current meeting, since multiple meetings could be using the same
# shared desktop, so the script currently assumes that only a single
# Big Blue Button meeting is running, and throws an exception
# otherwise.

import requests
import sys
from urllib.parse import urlencode, quote_plus
import argparse

from lxml import etree
import subprocess

from vnc_collaborate import bigbluebutton

import fnvhash

parser = argparse.ArgumentParser(description='Generate login URL for a Big Blue Button server')
parser.add_argument('-t', '--text', action="store_true",
                    help='output in text format')
args = parser.parse_args()

# Get the internal meeting ID and convert it to the Etherpad padID
# using the algorithm hard-wired into BBB's HTML5 client.

xml = bigbluebutton.getMeetings()

meetingIDs = xml.xpath('.//internalMeetingID')

if len(meetingIDs) != 1:
   raise "Can't find a unique Big Blue Button meeting"

padID = hex(fnvhash.fnv1a_32(meetingIDs[0].text.encode('ascii')))[2:]

# Get the APIKEY used to communicate with the Etherpad server.

f = open("/usr/share/etherpad-lite/APIKEY.txt")
key = f.read()
f.close()

# Retrieve the data and print it

payload = {'apikey' : key, 'padID' : padID}
result = urlencode(payload, quote_via=quote_plus)
if args.text:
   url = "http://localhost:9001/api/1/getText?" + result
   key = 'text'
else:
   url = "http://localhost:9001/api/1/getHTML?" + result
   key = 'html'
response = requests.get(url)
response.raise_for_status()
print(response.json()['data'][key])

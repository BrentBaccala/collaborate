#!/usr/bin/python3

import requests
import sys
from urllib.parse import urlencode, quote_plus

f = open("/usr/share/etherpad-lite/APIKEY.txt")
key = f.read()
f.close()

payload = {'apikey' : key}
result = urlencode(payload, quote_via=quote_plus)
url = "http://localhost:9001/api/1.2.1/listAllPads?" + result
response = requests.get(url)
response.raise_for_status()
#print(response.json())

lastEdited = {}

for padID in response.json()['data']['padIDs']:
   payload = {'apikey' : key, 'padID' : padID}
   result = urlencode(payload, quote_via=quote_plus)
   url = "http://localhost:9001/api/1.2.1/getLastEdited?" + result
   response2 = requests.get(url)
   response2.raise_for_status()
   #print(response2.json())
   lastEdited[response2.json()['data']['lastEdited']] = padID

for date in sorted(lastEdited):
   print(date, lastEdited[date])

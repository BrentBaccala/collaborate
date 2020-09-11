
import subprocess
import json
import re
from lxml import etree

from . import bigbluebutton

FS_CLI = "/opt/freeswitch/bin/fs_cli"

XML_CONF = "/opt/freeswitch/conf/autoload_configs/event_socket.conf.xml"

freeswitch_ids = {}
voiceBridge = None
mute_status = {}
deaf_status = {}

# get freeswitch authentication

with open(XML_CONF) as file:
    xml = etree.fromstring(file.read())
    freeswitch_pw = xml.xpath(".//param[@name='password']/@value")[0]


def get_status():

    # Fetch freeswitch conference data and map names to freeswitch id numbers

    global voiceBridge

    meetingInfo = bigbluebutton.getMeetingInfo(bigbluebutton.find_current_meeting())
    voiceBridge = meetingInfo.find("voiceBridge").text
    viewerIDs = [e.text for e in meetingInfo.xpath(".//role[text()='VIEWER']/../userID")]

    freeswitch_process = subprocess.Popen([FS_CLI, '-p', freeswitch_pw, '-x', 'conference json_list'], stdout=subprocess.PIPE)
    (stdoutdata, stderrdata) = freeswitch_process.communicate()
    try:
        conferences = json.loads(stdoutdata.decode())
    except json.JSONDecodeError:
        conferences  = []

    freeswitch_ids.clear()
    mute_status.clear()
    deaf_status.clear()

    for conf in conferences:
        if conf['conference_name'] == voiceBridge:
            for member in conf['members']:
                # Now we parse the freeswitch name and extract the BBB userId and fullName from it,
                # using a regular expression.  Brittle, I know.
                if 'caller_id_name' in member:
                    m = re.match(r'(?P<userID>\w*)_[0-9]*-bbbID(-LISTENONLY)?-(?P<fullName>.*)', member['caller_id_name'])
                    if m:
                        userID = m.group('userID')
                        fullName = m.group('fullName')
                        id = member['id']
                        # Only save viewer IDs, because we don't want to deaf/undeaf moderators at all
                        if userID in viewerIDs:
                            # allow lookup by full name, userID, or UNIX username
                            freeswitch_ids[fullName] = id
                            freeswitch_ids[userID] = id
                            UNIXname = bigbluebutton.fullName_to_UNIX_username(fullName)
                            if UNIXname:
                                freeswitch_ids[UNIXname] = id
                            mute_status[id] = not member['flags']['can_speak']
                            deaf_status[id] = not member['flags']['can_hear']

def print_status():
    get_status()
    print(freeswitch_ids)
    print('Mute:', mute_status)
    print('Deaf:', deaf_status)

def freeswitch_cmd(cmd):
    print(cmd)
    freeswitch_process = subprocess.Popen([FS_CLI, '-p', freeswitch_pw, '-x', cmd])
    freeswitch_process.wait()

def freeswitch_conference_cmd(*cmd):
    freeswitch_cmd('conference ' + voiceBridge + ' ' + ' '.join(map(str,cmd)))

def freeswitch_set_private(student_name):
    for id in freeswitch_ids.values():
        if student_name in freeswitch_ids and freeswitch_ids[student_name] == id:
            freeswitch_conference_cmd('undeaf', id)
            freeswitch_conference_cmd('unmute', id)
        else:
            freeswitch_conference_cmd('deaf', id)
            freeswitch_conference_cmd('mute', id)

def is_mute(student_name, default=None):
    try:
        return mute_status[freeswitch_ids[student_name]]
    except KeyError:
        return default

def is_deaf(student_name, default=None):
    try:
        return deaf_status[freeswitch_ids[student_name]]
    except KeyError:
        return default

def unmute_student(student_name):
    get_status()
    if student_name in freeswitch_ids:
        freeswitch_conference_cmd('unmute', freeswitch_ids[student_name])

def mute_student(student_name):
    get_status()
    if student_name in freeswitch_ids:
        freeswitch_conference_cmd('mute', freeswitch_ids[student_name])

def undeaf_student(student_name):
    get_status()
    if student_name in freeswitch_ids:
        freeswitch_conference_cmd('undeaf', freeswitch_ids[student_name])

def deaf_student(student_name):
    get_status()
    if student_name in freeswitch_ids:
        freeswitch_conference_cmd('deaf', freeswitch_ids[student_name])

def unmute_all():
    get_status()
    for id in freeswitch_ids.values():
        freeswitch_conference_cmd('unmute', id)

def mute_all():
    get_status()
    for id in freeswitch_ids.values():
        freeswitch_conference_cmd('mute', id)

def undeaf_all():
    get_status()
    for id in freeswitch_ids.values():
        freeswitch_conference_cmd('undeaf', id)

def deaf_all():
    get_status()
    for id in freeswitch_ids.values():
        freeswitch_conference_cmd('deaf', id)

def cmdline_operation(one_student_func, all_students_func, students):
    if len(students) == 0:
        print("Specify at least one student name, or -a for all")
    elif students[0] == '-a':
        all_students_func()
    else:
        for student in students:
            one_student_func(student)

def undeaf_students(students):
    cmdline_operation(undeaf_student, undeaf_all, students)
def deaf_students(students):
    cmdline_operation(deaf_student, deaf_all, students)
def unmute_students(students):
    cmdline_operation(unmute_student, unmute_all, students)
def mute_students(students):
    cmdline_operation(mute_student, mute_all, students)

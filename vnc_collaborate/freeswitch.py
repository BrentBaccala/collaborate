
import subprocess
import json
import re
from lxml import etree

FS_CLI = "/opt/freeswitch/bin/fs_cli"

XML_CONF = "/opt/freeswitch/conf/autoload_configs/event_socket.conf.xml"

freeswitch_ids = {}
conference = None
mute_status = {}
deaf_status = {}

# get freeswitch authentication

with open(XML_CONF) as file:
    xml = etree.fromstring(file.read())
    freeswitch_pw = xml.xpath(".//param[@name='password']/@value")[0]


def get_status():

    #
    # Fetch freeswitch conference data and map names to freeswitch id numbers
    #
    # We ONLY save student ids, because we don't want to mute/unmute teachers at all
    #
    # We also flatten names by removing spaces

    global conference

    freeswitch_process = subprocess.Popen([FS_CLI, '-p', freeswitch_pw, '-x', 'conference json_list'], stdout=subprocess.PIPE)
    (stdoutdata, stderrdata) = freeswitch_process.communicate()
    try:
        conference = json.loads(stdoutdata.decode())
    except:
        conference  = []

    freeswitch_ids.clear()
    mute_status.clear()
    deaf_status.clear()

    if len(conference) > 0:
        for member in conference[0]['members']:
            try:
                # Now we parse the freeswitch name and extract the BBB userId and fullName from it,
                # using a regular expression.  Brittle, I know.
                m = re.match(r'(?P<userID>\w*)-bbbID(-LISTENONLY)?-(?P<fullName>.*)', member['caller_id_name'])
                if m:
                    userID = m.group('userID')
                    fullName = m.group('fullName')
                    fullNameCamelCase = fullName.replace(' ', '')
                    id = member['id']
                    freeswitch_ids[fullNameCamelCase] = id
                    mute_status[member['id']] = not member['flags']['can_speak']
                    deaf_status[member['id']] = not member['flags']['can_hear']
            except:
                pass

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
    freeswitch_cmd('conference ' + conference[0]['conference_name'] + ' ' + ' '.join(map(str,cmd)))

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

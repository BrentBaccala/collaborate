
import subprocess
import json

FS_CLI = "/opt/freeswitch/bin/fs_cli"

freeswitch_ids = {}
conference = None

def get_freeswitch_ids():

    #
    # Fetch freeswitch conference data and map names to freeswitch id numbers
    #
    # We ONLY save student ids, because we don't want to mute/unmute teachers at all
    #
    # We also flatten names by removing spaces

    global conference

    freeswitch_process = subprocess.Popen([FS_CLI, '-x', 'conference json_list'], stdout=subprocess.PIPE)
    (stdoutdata, stderrdata) = freeswitch_process.communicate()
    try:
        conference = json.loads(stdoutdata.decode())
    except:
        conference  = []

    freeswitch_ids.clear()

    if len(conference) > 0:
        for member in conference[0]['members']:
            try:
                member_name = member['caller_id_name'].split('-bbbID-')[1].replace(' ', '')
                id = member['id']
                if 'DCPS' not in member_name:
                    freeswitch_ids[member_name] = id
            except:
                pass

get_freeswitch_ids()

mute_status = {}
deaf_status = {}
try:
    for member in conference[0]['members']:
        try:
            mute_status[member['id']] = not member['flags']['can_speak']
            deaf_status[member['id']] = not member['flags']['can_hear']
        except:
            pass
except:
    pass

print(freeswitch_ids)
print('Mute:', mute_status)
print('Deaf:', deaf_status)

def freeswitch_cmd(cmd):
    print(cmd)
    freeswitch_process = subprocess.Popen([FS_CLI, '-x', cmd])
    freeswitch_process.wait()

def freeswitch_conference_cmd(*cmd):
    freeswitch_cmd('conference ' + conference[0]['conference_name'] + ' ' + ' '.join(map(str,cmd)))

def unmute_all():
    for id in freeswitch_ids.values():
        freeswitch_conference_cmd('undeaf', id)
        freeswitch_conference_cmd('unmute', id)

def mute_all():
    for id in freeswitch_ids.values():
        freeswitch_conference_cmd('deaf', id)
        freeswitch_conference_cmd('mute', id)

def freeswitch_set_private(student_name):
    for id in freeswitch_ids.values():
        if student_name in freeswitch_ids and freeswitch_ids[student_name] == id:
            freeswitch_conference_cmd('undeaf', id)
            freeswitch_conference_cmd('unmute', id)
        else:
            freeswitch_conference_cmd('deaf', id)
            freeswitch_conference_cmd('mute', id)

def unmute_student(student_name):
    if student_name in freeswitch_ids:
        freeswitch_conference_cmd('undeaf', freeswitch_ids[student_name])
        freeswitch_conference_cmd('unmute', freeswitch_ids[student_name])

def mute_student(student_name):
    if student_name in freeswitch_ids:
        freeswitch_conference_cmd('deaf', freeswitch_ids[student_name])
        freeswitch_conference_cmd('mute', freeswitch_ids[student_name])


import sys
from vnc_collaborate import *
from vnc_collaborate import fvwm_configs

# print('vnc_collaborate:', sys.argv)

try:
    import importlib.resources as pkg_resources
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    # need to run 'pip3 install importlib-resources' to get this
    import importlib_resources as pkg_resources

if len(sys.argv) > 1:
    if sys.argv[1] == 'teacher_desktop':
        teacher_desktop(*sys.argv[2:])
    elif sys.argv[1] == 'teacher_zoom':
        teacher_zoom(*sys.argv[2:])
    elif sys.argv[1] == 'student_audio_controls':
        student_audio_controls(*sys.argv[2:])
    elif sys.argv[1] == 'undeaf_students':
        undeaf_students(sys.argv[2:])
    elif sys.argv[1] == 'deaf_students':
        deaf_students(sys.argv[2:])
    elif sys.argv[1] == 'unmute_students':
        unmute_students(sys.argv[2:])
    elif sys.argv[1] == 'mute_students':
        mute_students(sys.argv[2:])
    elif sys.argv[1] == 'websockify':
        websockify()
    elif sys.argv[1] == 'print':
        if sys.argv[2] =='teacher_mode_fvwm_config':
            print(pkg_resources.read_text(fvwm_configs, 'teacher-mode'))
        elif sys.argv[2] =='teacher_fvwm_config':
            print(pkg_resources.read_text(fvwm_configs, 'teacher'))
        elif sys.argv[2] =='student_fvwm_config':
            print(pkg_resources.read_text(fvwm_configs, 'student'))
        elif sys.argv[2] =='student_sandbox_fvwm_config':
            print(pkg_resources.read_text(fvwm_configs, 'student-sandbox'))
        else:
            print("Unknown resource:", sys.argv[2])
    else:
        print("Unknown operation:", sys.argv[1])

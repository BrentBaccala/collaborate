
import sys
from vnc_collaborate import *

try:
    import importlib.resources as pkg_resources
except ImportError:
    # Try backported to PY<37 `importlib_resources`.
    # need to run 'pip3 install importlib-resources' to get this
    import importlib_resources as pkg_resources

if sys.argv[1] == 'teacher_desktop':
    teacher_desktop(sys.argv[2], sys.argv[3])
elif sys.argv[1] == 'print':
    if sys.argv[2] =='teacher_mode_fvwm_config':
        print(pkg_resources.read_text(__package__, 'teacher-mode-fvwm-config'))

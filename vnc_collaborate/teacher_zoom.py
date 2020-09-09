#
# Usage: teacher-zoom(WINDOW-NAME)
#
# Called from fvwm when a student desktop is clicked in a teacher desktop view,
# this script is passed the window name of the miniaturized view-only student window
# on the teacher desktop (which was created by the teacher-desktop script).
#
# We decode the window name (which is the default SSVNC window name) to figure
# out the user name and desktop number in order to launch a full-screen,
# fully interactive view of the student desktop, so that the teacher can
# interact with it.
#
# We also check to see if the student was deafed, and if so undeaf him/her
# on entry, then re-deaf the student after the full-screen view exits.

import sys
import re
import subprocess

import vnc_collaborate.freeswitch as freeswitch

def teacher_zoom(window):

   # See FVWM man page on $[w.name] - the window name is encased in single quotes
   # and embedded single quotes are escaped with a backspace.  The window name
   # created in the teacher_desktop.py script has the fields separated by semicolons.
   # So, this expression undoes the FVWM quoting and splits apart our arguments.

   args = window.replace("\\'", "'")[1:-1].split(';')

   if len(args) == 3 and args[0] == 'TeacherViewVNC':

      STUDENT_ID = args[1]
      STUDENT_DISPLAY = args[2]

      print(STUDENT_ID, STUDENT_DISPLAY)

      freeswitch.print_status()

      was_deafed = freeswitch.is_deaf(STUDENT_ID, default=False)

      # If the student was deafed, undeaf him, since we're probably about to talk to him/her
      if was_deafed:
         freeswitch.undeaf_student(STUDENT_ID)

      # XXX Teacher desktop geometry is hard-wired here!

      args = ['ssvncviewer', '-title', 'Zoomed Student Desktop',
              '-geometry', '1476x830', '-scale', '1476x830',
              '-escape', 'Alt_L', '-passwd', '/home/baccala/.vnc/passwd',
              STUDENT_DISPLAY]
      print(args)

      proc = subprocess.Popen(args)
      proc.wait()

      # Re-deaf and mute the student, but ONLY if he/she was deafed originally
      if was_deafed:
         #freeswitch.mute_student(STUDENT_ID)
         freeswitch.deaf_student(STUDENT_ID)

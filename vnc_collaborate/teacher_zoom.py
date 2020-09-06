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
   match = re.search(r'([^ ]*)\\\'s X desktop \((osito:[0-9]*)', window)

   if match:

      STUDENT = match.group(1)
      STUDENT_DISPLAY = match.group(2)

      print(STUDENT, STUDENT_DISPLAY)

      was_deafed = freeswitch.is_deaf(STUDENT, default=False)

      # If the student was deafed, undeaf him, since we're probably about to talk to him/her
      if was_deafed:
         freeswitch.undeaf_student(STUDENT)

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
         freeswitch.mute_student(STUDENT)
         freeswitch.deaf_student(STUDENT)

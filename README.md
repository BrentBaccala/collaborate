This is a extension to the
[Big Blue Button](https://bigbluebutton.org/) video conferencing
system to facilitate virtual classrooms by allowing VNC remote
desktops to be shared in a video conference.

This extension itself is housed in the
[BrentBaccala/bigbluebutton](https://github.com/BrentBaccala/bigbluebutton)
repository.  This repository contains Python support code,
but is also the home of the install instructions and the issue tracker.

The extension allows different VNC desktops to be presented to different
participants, each of whom is given a Linux login on the video
conferencing server.

*For security purposes, it's probably best to
think about this extension as a login method that allows UNIX users
to collaborate among themselves in video conferences.*

There is also a "teacher mode" that allows moderators to
observe all student desktops running in a Big Blue Button session and
interact with them individually.  When a student's desktop is selected
(by clicking on it), that student desktop becomes full screen on the
teacher desktop, and the session audio is undeafed for that student
only.  Pressing an escape sequence (ALT-SHIFT-Q) returns the teacher
to the overview mode, and re-deafs the student.

Here's a screenshot of "teacher mode" with four students connected:

![screenshot of a running demo](demo.jpg)

A more basic use of this software is to share a VNC remote desktop
among the participants in a video conference.

For more information, see the [Wiki](../../wiki), in particular the
[installation instructions](../../wiki/Install).

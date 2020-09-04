This is a collection of scripts and programs to facilitate a virtual
classroom based on Big Blue Button and VNC remote desktops.

**How to use these scripts**

1. Install Big Blue Button

   My most reliable configuration uses the bbb-install script on an Amazon EC2 instance.

   SSL configuration is required

1. Configure authentication into Big Blue Button

1. Clone the BrentBaccala/bigbluebutton repository

1. `npm install`

1. Shut down the bbb-html5 service and run `npm start`

1. `apt install fvwm` (the window manager)

1. `apt install tightvncserver` and start a VNC remote desktop with `vncserver`

1. `apt install websockify` and start websockify to relay WebSock connections to the VNC server

1. from a Big Blue Button session, "share remote desktop" and use the URL "wss://HOST:PORT/"

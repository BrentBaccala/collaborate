This is a collection of scripts and programs to facilitate a virtual
classroom based on Big Blue Button and VNC remote desktops.

**How to use these scripts**

1. Install Big Blue Button

   My most reliable configuration uses the bbb-install script from the bigbluebutton/bbb-install
   repository on an Amazon EC2 instance running Ubuntu 16.  Start an c5.2xlarge instance
   based on ami-05e16100b6f337dda (standard Ubuntu 16), arrange for a DNS name to point
   to the instance (I control freesoft.org and use Google dynamic DNS; the ddclient
   program runs on my instance to register the IP address with Google), then download
   and run bbb-install, something like this:

   `sudo ./bbb-install.sh -v xenial-22 -s collaborate.freesoft.org -e cosine@freesoft.org`

   or this, if you've already got SSL keys and certificates:

   `sudo ./bbb-install.sh -v xenial-22 -s collaborate.freesoft.org -d`

   SSL configuration is required

1. Configure authentication into Big Blue Button

   There are many ways to do this.  Installing Greenlight by adding the -g switch to
   the bbb-install.sh call is probably the simplest.  Check the Greenlight documentation
   for more information about what to do next (like adding users).

1. Clone the BrentBaccala/bigbluebutton repository

1. In the repository clone's bigbluebutton-html5 directory, run `npm install`

   This downloads and installs the various node.js dependencies.

   You'll also need to get the `noVNC-node` repository from my github - currently points to a local source directory.

1. Shut down the standard bbb-html5 service

   `sudo systemctl stop bbb-html5`

   `sudo systemctl disable bbb-html5` (prevents it from starting again on boot)

1. In the clone's bigbluebutton-html5 directory, run `npm start`

   You should now have a working Big Blue Button installation with a new menu option to "share remote desktop"

1. `apt install fvwm` (the window manager)

1. `apt install tightvncserver` and start a VNC remote desktop with `vncserver`

1. `apt install websockify` and start websockify to relay WebSock connections to the VNC server

1. from a Big Blue Button session, "share remote desktop" and use the URL "wss://HOST:PORT/"

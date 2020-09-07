This is a collection of scripts and programs to facilitate a virtual
classroom based on Big Blue Button and VNC remote desktops.

**How to use these scripts**

1. Install Big Blue Button

   My most reliable configuration uses the bbb-install script from the bigbluebutton/bbb-install
   repository on an Amazon EC2 instance running Ubuntu 16.  Start an c5.2xlarge instance
   based on ami-05e16100b6f337dda (standard Ubuntu 16), at least 16 GB disk space (12 GB is required
   for bare-bones installation), a fairly open security group, arrange for a DNS name to point
   to the instance (I control freesoft.org and use Google dynamic DNS; the ddclient
   program runs on my instance to register the IP address with Google), then download
   and run bbb-install, something like this:

   `sudo ./bbb-install.sh -v xenial-22 -s collaborate.freesoft.org -e cosine@freesoft.org`

   or this, if you've already got SSL keys and certificates:

   `sudo ./bbb-install.sh -v xenial-22 -s collaborate.freesoft.org -d`

   SSL configuration is required for proper operation of Big Blue Button.

1. Configure authentication into Big Blue Button

   There are many ways to do this.  Installing Greenlight by adding the -g switch to
   the bbb-install.sh call is probably the simplest.  Check the Greenlight documentation
   for more information about what to do next (like adding users).  The default
   Greenlight configuration allows anybody to sign up as a user, but moderators
   need to be added from the command line.

1. Clone the [BrentBaccala/bigbluebutton](https://github.com/BrentBaccala/bigbluebutton) repository (not this one)

1. In the repository clone's bigbluebutton-html5 directory, run `npm install npm-force-resolutions`, then `npm install`

   This downloads and installs the various node.js dependencies.

1. We also need `meteor npm install --save bowser` at the moment

1. Install Meteor: `curl https://install.meteor.com/ | sh`

1. Select Meteor 1.8: `meteor update --allow-superuser --release 1.8`

1. Update the Kurento URL in the settings file:

   ``WSURL=`yq r /usr/share/meteor/bundle/programs/server/assets/app/config/settings.yml public.kurento.wsUrl` ``

   `sed -i.bak "s|\bHOST\b|$WSURL|" private/config/settings.yml`

1. Install Meteor dependencies: `meteor npm install`

1. Shut down the standard bbb-html5 service

   `sudo systemctl stop bbb-html5`

   `sudo systemctl disable bbb-html5` (prevents it from starting again on boot)

1. In the clone's bigbluebutton-html5 directory, run `npm start`

   You should now have a working Big Blue Button installation with a new menu option to "share remote desktop".

   To keep `npm start` running, I either run it in a `screen` session, or install `pm2` and run it from there (how?).

   `pm2` can be made persistent pretty easily (run `pm2 startup` for instructions)

1. Now clone this repository, and from its directory...

1. Install dependencies: `sudo apt install fvwm tightvncserver websockify`

1. Build the `vnc_collaborate` module: `./setup.py build`

1. Install the `vnc_collaborate` module: `pip3 install .`

1. Check that it installed correctly: `python3 -m vnc_collaborate` should run with no output and no error

1. Use the following one-line config for the teacher account's `.fvwm/config` file:

   `PipeRead 'python3 -m vnc_collaborate print teacher_fvwm_config'`

   The FVWM config is shipped with the Python package, and this pulls in the config
   without having to hard-wire the location where the package is installed.

1. Start the teacher's VNC desktop with `vncserver` with something like:

   `vncserver -geometry 1024x768 :1`

   The first time it will prompt you to set a password.  A view-only password is not really recommended,
   since we almost always want to interact with our desktops from Big Blue Button.

1. Start websockify to relay WebSock connections to the VNC server, something like this:

   `websockify -D --ssl-only --cert $HOME/ssl/fullchain1.pem --key $HOME/ssl/privkey1.pem 6101 localhost:5901`

   Notice that special arrangements have been made (I copied the SSL keys and certs from
   `/etc/letsencrypt/archive` into my home directory)
   to enable encrypted connections.

1. From a Big Blue Button session, "share remote desktop" and use the URL "wss://HOST:PORT/?password=PASSWORD"

   If you're following the example, PORT is 6101.

   At this point, the teacher desktop should be working.

   Probably want to install and run `gnome-settings-daemon` and `gnome-tweak-tool`
   (run both inside the desktop) to set your fonts.

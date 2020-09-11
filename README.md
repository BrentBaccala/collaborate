This is a collection of scripts and programs to facilitate a virtual
classroom based on [Big Blue Button](https://bigbluebutton.org/) and
VNC remote desktops.

I've developed an extension to the Big Blue Button video conferencing
system that allows VNC remote desktops to be shared in a video
conference, much like a screenshare.  This extension is housed
in the [BrentBaccala/bigbluebutton](https://github.com/BrentBaccala/bigbluebutton) repository.

Once the VNC extension is installed, the Python package in this
repository allows different VNC desktops to be presented to different
participants, based on a dispatch table contained in a Postgres SQL
database.  There is also a "teacher mode" that allows moderators to
observe all student desktops running in a Big Blue Button session and
interact with them individually.  When a student's desktop is selected
(by clicking on it), that student desktop becomes full screen on the
teacher desktop, and the session audio is undeafed for that student
only.  Pressing an escape sequence (ALT-SHIFT-Q) returns the teacher
to the overview mode, and re-deafs the student.

Here's a screenshot of "teacher mode" with four students connected:

![screenshot of a running demo](demo.jpg)

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

1. Build the `vnc_collaborate` module: `./setup.py build`

1. Install the `vnc_collaborate` module: `sudo -H pip3 install .`

   It's installed globally so that both the student and teacher accounts have access to it.

1. You also need to install the `websockify` module, but it's not installed automatically because
   it has a dependency problem on Ubuntu 16.  Run this to install it:

   `sudo -H pip3 install --no-deps websockify`

1. You need to install one or the other of `psycopg2` or `psycopg2-binary`; same syntax, i.e:

   `sudo -H pip3 install psycopg2-binary`

1. Check that `vnc_collaborate` installed correctly: `python3 -m vnc_collaborate` should run with no output and no error

1. Install packages needed to run VNC desktops: `sudo apt install fvwm tightvncserver ssvnc`

   Only the window manager (FVWM), the VNC server, and the VNC viewer (ssvnc) are strictly *required*,
   but some other packages are useful:

   1. A terminal; `sudo apt install gnome-terminal`
   1. A web browser; `sudo apt install firefox`
   1. A whiteboard; `sudo apt install xournal`
   1. anything else you'd like to run on your desktops

1. Use the following one-line config for the teacher account's `.fvwm/config` file:

   `PipeRead 'python3 -m vnc_collaborate print teacher_fvwm_config'`

   The FVWM config is shipped with the Python package, and this pulls in the config
   without having to hard-wire the location where the package is installed.

1. Start the teacher's VNC desktop with `vncserver` with something like:

   `vncserver -geometry 1024x768 :1`

   The first time it will prompt you to set a password (do so).  It will also ask if you want to set a view-only password,
   which is not really recommended,
   since we almost always want to interact with our desktops from Big Blue Button.

1. Start websockify to relay WebSock connections to the VNC server, something like this:

   `python3 -m vnc_collaborate websockify -D --ssl-only --cert $HOME/ssl/fullchain1.pem --key $HOME/ssl/privkey1.pem 6101 localhost:5901`

   I often run this command in a `screen` session without the `-D` option if I want to monitor its operation.

   Notice that special arrangements have been made (I copied the SSL keys and certs from
   `/etc/letsencrypt/archive` into my home directory)
   to enable encrypted connections.

   Also note that we're using a special websockify built-in to the `vnc_collaborate` module.
   This custom websockify will relay VNC connections to different VNC servers based on a UNIX user name
   that can be (optionally) provided in the URL (see below).

1. At this point, the teacher desktop should be working.  You don't need to do anything in SQL yet,
   since without the SQL table all connections will fall through to the default host and port (`localhost:5901` in
   this example).

   From a Big Blue Button session, "share remote desktop" and use the URL `wss://HOST:PORT/?password=PASSWORD`

   If you're following the example, PORT is 6101.

1. Inside the teacher (and the student) desktops, you probably want to run `gnome-settings-daemon` in background,
   to permit control over the display fonts.

   You might need to install the program: `sudo apt install gnome-settings-daemon`.

   I then like to run `gsettings set org.gnome.desktop.interface font-name 'Monospace 16'` to set the fonts
   on the menus.  The title bar fonts are set in the FVWM config file.

   You can also install and run `gnome-tweak-tool`, which is a GUI interface to these settings.

1. To use student desktops, you'll need to configure a Postgres table.
   The user 'vnc' with password 'vnc' and database 'greenlight_production'
   is currently hard-wired into the scripts for Postgres authentication,
   so it's best to install Greenlight
   and create this role using a tool like `psql` or `pgadmin3`
   (authenticate using the credentials in the Greenlight `.env` file):

   `CREATE ROLE vnc LOGIN PASSWORD 'vnc';`

   Create the table (or view) using the following SQL command:

   `CREATE TABLE VNCusers(VNCuser text, UNIXuser text, PRIMARY KEY (VNCuser))`

   The only permission 'vnc' needs is to read this table:

   `GRANT SELECT ON VNCusers to vnc;`

   The grant isn't too broad, since it only allows read-only access to this one table,
   and the default Greenlight configuration (the port mapping in its docker-compose.yml file)
   only allows connections from localhost.

1. Create UNIX user accounts for the students.

1. Use `psql` or `pgadmin3` to add entries into the `VNCusers` table
   mapping the Big Blue Button names to the UNIX usernames.

   If they're setup right, run a query and you should see something like this:

   ```
   $ psql -h localhost -U postgres -d greenlight_production -c "select * from vncusers"
            vncuser        |   unixuser   
    -----------------------+--------------
     Baccala, Brent (DCPS) | baccala
     Charlie Clown         | CharlieClown
     Jimmy Brown           | JimmyBrown
     Freddy Frown          | FreddyFrown
     Nancy Noun            | NancyNoun
    (5 rows)
   ```

1. Start vnc servers for the various students, something like:

   `sudo su CharlieClown vncserver -geometry 1024x768`

   They all have to have the same password, currently.  I usually achieve this by putting a copy of my
   `.vnc/passwd` file in `/etc/skel/.vnc/passwd` (permissions must be 600 or 400 or vncserver won't take it).
   Then new users created with `adduser` will get a copy of this file in their newly created home directories.

1. From Big Blue Button, "share remote desktop" with a URL like `wss://HOST:PORT/{fullName}?password=PASSWORD`

   The Big Blue Button clients will replace `{fullName}` with the BBB user name, and the customized
   websockify will use the database to map to UNIX user names and relay the connections to the correct user.

   The host and port specified as the last option to the `websockify` command now become a default VNC session
   that users will connect to if the username lookup fails.

1. There is currently no mechanism to auto-start VNC servers from these scripts.  If they're not
   running, the user will fall back on the default VNC session.

1. To facilitate full screen use, the students can run an audio control widget in their student desktops:

   `python3 -m vnc_collaborate student_audio_controls &`

   The widget contains mute and deaf controls for that single student, as well as a "hand" icon that does
   not interface with Big Blue Button at all, but is visible from the teacher overview when it is clicked.

   This widget is available as a menu option in the standard student FVWM config (see below).

1. The student desktops also need a window manager of some kind.  FVWM is not required, since it doesn't
   have to support any special features like "teacher mode".  If FVWM is used, two student
   FVWM configs are provided:

   1. A standard FVWM config.  The following command can be placed
      in the student's `.fvwm/config` file, or in `/etc/skel/.fvwm/config`:

      `PipeRead 'python3 -m vnc_collaborate print student_fvwm_config'`

   1. A minimalist FVWM config that offers very few options to the student.  The following command can be placed
      in the student's `.fvwm/config` file, or in `/etc/skel/.fvwm/config`:

      `PipeRead 'python3 -m vnc_collaborate print student_sandbox_fvwm_config'`

   If FVWM is used with a different config, I recommend at least setting `EdgeScroll 0 0`, since edge
   scrolling (panning to a new desktop when the mouse hits the edge of the display) doesn't work
   very well on VNC desktops.

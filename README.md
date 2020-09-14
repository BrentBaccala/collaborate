This is a pip-installable Python module to facilitate a virtual
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

**How to use this package**

1. Install Big Blue Button

   My most reliable configuration uses the bbb-install script from the bigbluebutton/bbb-install
   repository on an Amazon EC2 instance running Ubuntu 16.  Start an c5.2xlarge instance
   based on ami-05e16100b6f337dda (standard Ubuntu 16), at least 16 GB disk space (12 GB is required
   for bare-bones installation), a fairly open security group, arrange for a DNS name to point
   to the instance (I control freesoft.org and use Google dynamic DNS; the ddclient
   program runs on my instance to register the IP address with Google), then download
   and run bbb-install, something like this:

   `sudo ./bbb-install.sh -v xenial-22 -s collaborate.freesoft.org -g -e cosine@freesoft.org`

   or this, if you've already got SSL keys and certificates:

   `sudo ./bbb-install.sh -v xenial-22 -s collaborate.freesoft.org -g -d`

   SSL configuration is required for proper operation of Big Blue Button.

1. Configure authentication into Big Blue Button

   There are many ways to do this.  Installing Greenlight (the `-g`
   switch on the bbb-install.sh call above) is probably the simplest.
   Check the Greenlight documentation for more information about what
   to do next (like adding users).  The default Greenlight
   configuration allows anybody to sign up as a user, but moderators
   need to be added from the command line.

   Installing Greenlight also installs a Postgres server (both in
   docker containers), which is handy because we need Postgres to
   manage our user lookup table.  In fact, the database name
   `greenlight_production` is (currently) hard-wired in the package.

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

   To keep `npm start` running, I either run it in a `screen` session, or install `pm2` and run it like this:

   `pm2 start npm -- start`

   `pm2` can be made persistent pretty easily (run `pm2 startup` for instructions)

1. Now clone this repository, and from its directory...

1. Build the `vnc_collaborate` module: `./setup.py build`

   You might be missing some packages to make this work:

   ```
   sudo apt install python3-pip
   pip3 install setuptools
   ./setup.py build
   ```

1. Install the `vnc_collaborate` module: `sudo -H pip3 install .`

   It's installed globally so that both the student and teacher accounts have access to it.

1. You also need to install the `websockify` module, but it's not installed automatically because
   it has a dependency problem on Ubuntu 16.  Run this to install it:

   `sudo -H pip3 install --no-deps websockify`

1. You need to install one or the other of `psycopg2` or `psycopg2-binary`; same syntax, i.e:

   `sudo -H pip3 install psycopg2-binary`

1. You need to install an apt package to get the X11 Tk library:

   `sudo apt install python3-tk`

1. Check that `vnc_collaborate` installed correctly: `python3 -m vnc_collaborate` should run with no output and no error

1. Install packages needed to run VNC desktops: `sudo apt install fvwm tightvncserver ssvnc`

   Only the window manager (FVWM), the VNC server, and the VNC viewer (ssvnc) are strictly *required*,
   but some other packages are useful:

   1. A terminal; `sudo apt install gnome-terminal`
   1. A web browser; `sudo apt install firefox`
   1. A whiteboard; `sudo apt install xournal`
   1. anything else you'd like to run on your desktops

1. Create a UNIX account for the teacher using something like:

   `sudo adduser --force-badname BrentBaccala`

   There's no naming convention that has to be followed here, the account doesn't have to be given a password
   (you'll be prompted for a VNC password in a moment), and I needed `--force-badname` only because the
   name I choose didn't pass Ubuntu's standard account name regular expression test.

   If just hit return six times when prompted for a password, it will create the account with no password.

1. Use the following one-line config for the teacher account's `.fvwm/config` file:

   `PipeRead 'python3 -m vnc_collaborate print teacher_fvwm_config'`

   The FVWM config is shipped with the Python package, and this pulls in the config
   without having to hard-wire the location where the package is installed.

   At the moment, there isn't much privilege separation between a teacher account and a student account.
   A teacher account is only a teacher account by virtue of using the teacher FVWM config.

   Since we need to use the same VNC password for all desktops at the moment, it isn't that hard
   for a student to access the teacher's desktop anyway.

1. Start the teacher's VNC desktop with `vncserver` with something like:

   `sudo -u BrentBaccala -i vncserver`

   The first time it will prompt you to set a password (do so).  It will also ask if you want to set a view-only password,
   which is not really recommended,
   since we almost always want to interact with our desktops from Big Blue Button.

1. Start websockify to relay WebSock connections to the VNC server, something like this:

   `python3 -m vnc_collaborate websockify -D --ssl-only --cert $HOME/ssl/fullchain1.pem --key $HOME/ssl/privkey1.pem 6101 localhost:5901`

   I often run this command in a `screen` session without the `-D` option if I want to monitor its operation.

   Notice that special arrangements have been made (I copied the SSL keys and certs from
   `/etc/letsencrypt/archive` into my home directory)
   to enable encrypted connections.  Reading these SSL files is the only special permission
   that `websockify` needs.

   Also note that we're using a special websockify built-in to the `vnc_collaborate` module.
   This custom websockify will relay VNC connections to different VNC servers based on a UNIX user name
   that can be (optionally) provided in the URL (see below).

1. At this point, the teacher desktop should be working.  You don't need to do anything in SQL yet,
   since without the SQL table all connections will fall through to the default host and port (`localhost:5901` in
   this example).

   From a Big Blue Button session, "share remote desktop" and use the URL `wss://HOST:PORT/?password=PASSWORD`

   If you're following the example, PORT is 6101.

   If you get `handler exception: [Errno 13] Permission denied` from the `websockify`
   (you'd have to run it without the `-D` option to see any messages from it at all),
   double-check the permissions on your SSL files.

1. Inside the teacher (and the student) desktops, you probably want to run `gnome-settings-daemon` in background,
   to permit control over the display fonts.

   You might need to install the program: `sudo apt install gnome-settings-daemon`.

   I then like to run `gsettings set org.gnome.desktop.interface font-name 'Monospace 16'` to set the fonts
   on the menus.  The title bar fonts are set in the FVWM config file.  The font used by `gnome-terminal`
   can be set either from its preferences dialog or by running
   `gsettings set org.gnome.desktop.interface monospace-font-name 'Monospace 16'.

   You can also install and run `gnome-tweak-tool`, which is a GUI interface to these settings.

1. To use student desktops, you'll need to configure a Postgres table.
   The user 'vnc' with password 'vnc' and database 'greenlight_production'
   is currently hard-wired into the package for Postgres authentication,
   so it's best to install Greenlight
   and create this role using a tool like `psql` or `pgadmin3`
   (authenticate using the credentials in the Greenlight `.env` file):

   `CREATE ROLE vnc LOGIN PASSWORD 'vnc';`

   Create the table (or view) using the following SQL command:

   `CREATE TABLE VNCusers(VNCuser text, UNIXuser text, PRIMARY KEY (VNCuser));`

   The only permission 'vnc' needs is to read this table:

   `GRANT SELECT ON VNCusers to vnc;`

   The grant isn't too broad, since it only allows read-only access to this one table,
   and the default Greenlight configuration (the port mapping in its docker-compose.yml file)
   only allows connections from localhost.

1. Prior to creating UNIX user accounts for the students, it is useful to put any files that
   should be copied to all of the student home directories in `/etc/skel`.  I find it
   particularly useful to put a copy of the `.vnc/passwd` file there (in `/etc/skel/.vnc/passwd`),
   making sure to set the permissions of `/etc/skel/.vnc` to 700 and `/etc/skel/.vnc/passwd` to 600,
   as well as `/etc/skel/.fvwm/config` (pick one of the two options outlined below).

1. Create UNIX user accounts for the students.  No passwords need be set.

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

1. Arrange to start VNC servers for the various students.

   The servers all have to have the same password, currently.  I usually achieve this by putting a copy of my
   `.vnc/passwd` file in `/etc/skel/.vnc/passwd` (permissions must be 600 or 400 or vncserver won't take it).
   Then new users created with `adduser` will get a copy of this file in their newly created home directories.

   If the SQL table contains a mapping from a Big Blue Button user to a UNIX user, but no running VNC server
   is found for that user, the `websockify` script will attempt to start one by running `sudo -u USER -i vncserver`.

   If this feature is desired, then `websockify` must be run with permission to execute this `sudo` operation.
   The simplest way to do this is to run `websockify` from an account (`ubuntu` on an AWS EC2 instance) that
   can execute *any* operation as *any* user, but this may present too much of a security risk.  Instead,
   `websockify` can be run from a user account with only permission to run `vncserver`, and only for student
   accounts.  See the `sudoers` man page for documentation on how to set this up.

   If this feature is not enabled (i.e, `websockify` is unable to execute the `sudo`), then the student VNC
   servers must be started in some other way.

1. From Big Blue Button, "share remote desktop" with a URL like `wss://HOST:PORT/{fullname}?password=PASSWORD`

   The Big Blue Button clients will replace `{fullname}` with the BBB user name, and the customized
   websockify will use the database to map to UNIX user names and relay the connections to the correct user.

   The host and port specified as the last option to the `websockify` command now become a default VNC session
   that users will connect to if the username lookup fails.

1. If the VNC servers receive too many connection attempts that fail authentication, they will start
   rejecting any connection attempt until a timer expires, and the timer will never expire if continued
   attempts are made to hack in the server.  I address this issue by blocking all attempts to connect
   directly to the VNC port range except on the loopback interface:

   `sudo iptables -A INPUT -p tcp -m tcp --dport 5900:5999 \! -i lo -j DROP`

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

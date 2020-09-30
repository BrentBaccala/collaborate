#!/usr/bin/perl
#
#  Copyright (C) 2004-2006,2008-2009 Ola Lundqvist <opal@debian.org>
#  Copyright (C) 2002-2009 Constantin Kaplinsky.  All Rights Reserved.
#  Copyright (C) 1999 AT&T Laboratories Cambridge.  All Rights Reserved.
#
#  This is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This software is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this software; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307,
#  USA.
#

# This file was heavily edited by
#              Ola Lundqvist <opal@debian.org>
#               Marcus Brinkmann <Marcus.Brinkmann@ruhr-uni-bochum.de>
# Clean option by Dirk Eddelbuettel <edd@debian.org>

# Please report all errors to Debian and not to ORL.

#
# vncserver - wrapper script to start an X VNC server.
#

# First make sure we're operating in a sane environment.

&SanityCheck();

# Default configuration of the TightVNC Server:

$geometry = "1024x768";
$depth = 24;
$desktopName = "X";
if (-d "/usr/share/tightvnc-java") {
    $vncClasses = "/usr/share/tightvnc-java";
}
$vncUserDir = "$ENV{HOME}/.vnc";
#$fontPath = "unix/:7100";
$authType = "-rfbauth $vncUserDir/passwd";

# Read configuration from the system-wide and user files if present.

$configFile = "/etc/tightvncserver.conf";
ReadConfiguration();
$configFile = "$ENV{HOME}/.vnc/tightvncserver.conf";
ReadConfiguration();

# Done reading configuration.

$defaultXStartup
    = ("#!/bin/sh\n\n".
       "xrdb \$HOME/.Xresources\n".
       "xsetroot -solid grey\n".
       "#x-terminal-emulator -geometry 80x24+10+10 -ls -title \"\$VNCDESKTOP Desktop\" &\n".
       "#x-window-manager &\n".
       "# Fix to make GNOME work\n".
       "export XKL_XMODMAP_DISABLE=1\n".
       "/etc/X11/Xsession\n");

$xauthorityFile = "$ENV{XAUTHORITY}";

######## Adding configuration possibility ################
$Config_file = "/etc/vnc.conf";
&ReadConfigFile();
$Config_file = "$ENV{HOME}/.vncrc";
&ReadConfigFile();

if (!$XFConfigPath) {
  foreach ("/etc/X11/xorg.conf", "/etc/X11/XF86Config-4", "/etc/X11/XF86Config" ){
      $XFConfigPath = $_;
      last if ( -e $XFConfigPath );
  }
}
if (!$fontPath) {
  &ReadXFConfigFont;
}
if (!$fontPath) {
  $fontPath = "/usr/share/fonts/X11/misc/,".
              "/usr/share/fonts/X11/Type1/,".
              "/usr/share/fonts/X11/75dpi/,".
              "/usr/share/fonts/X11/100dpi/"
}
if (!$colorPath) {
  &ReadXFConfigColor;
}
if (!$colorPath) {
  foreach ("/etc/X11/rgb", "/usr/share/X11/rgb", "/usr/X11R6/lib/X11/rgb"){
      $colorPath = $_;
      last if ( -e "${colorPath}.txt" );
  }
}
##########################################################

$vncUserDirUnderTmp = ($vncUserDir =~ m|^/tmp/.+|) ? 1 : 0;
$xstartup = ($vncUserDirUnderTmp) ?
  "$ENV{HOME}/.vncstartup" : "$vncUserDir/xstartup";
$xstartup = $vncStartup if ($vncStartup);
unless ($xauthorityFile) {
    if ($vncUserDirUnderTmp) {
        $xauthorityFile = "$vncUserDir/.Xauthority";
    } else {
        $xauthorityFile = "$ENV{HOME}/.Xauthority";
    }
}

chop($host = `uname -n`);


# Check command line options

&ParseOptions("-geometry",1,"-depth",1,"-pixelformat",1,"-name",1,"-kill",1,
	      "-help",0,"-h",0,"--help",0,
	      "-clean",0, "-fp",1,
              "-alwaysshared",0, "-nevershared",0,
              "-httpport",1,"-basehttpport",1);

&Usage() if ($opt{'-help'} || $opt{'-h'} || $opt{'--help'});

&Kill() if ($opt{'-kill'});

$useClasses = 0;
if (defined $vncClasses) {
  if(! -d $vncClasses) {
    die "VNC class files can not be found at $vncClasses.";
  }
  $useClasses = 1;
}

# Uncomment this line if you want default geometry, depth and pixelformat
# to match the current X display:
# &GetXDisplayDefaults();

if ($opt{'-geometry'}) {
    $geometry = $opt{'-geometry'};
}
if ($opt{'-depth'}) {
    $depth = $opt{'-depth'};
    $pixelformat = "";
}
if ($opt{'-pixelformat'}) {
    $pixelformat = $opt{'-pixelformat'};
}

if ($opt{'-fp'}) {
    @fontPathElements = split(/\s*,\s*/, "$opt{'-fp'}");

    $fontPath = '';

    foreach $i (0.."$#fontPathElements") {
        $tempFontPath = $fontPathElements[$i];
        if ($tempFontPath !~ m!^[^/]*/[^/]*:\d+$!) {
            $tempFontPath =~ s/:unscaled$//;
            if (-r "$tempFontPath/fonts.dir") {
                $fontPath .= "$fontPathElements[$i],";
            }
        } else {
            $fontPath .= "$fontPathElements[$i],";
        }
    }
    chop $fontPath;
}

&CheckGeometryAndDepth();

if ($opt{'-name'}) {
    $desktopName = $opt{'-name'};
}

# Create the user's vnc directory if necessary.

unless (-e $vncUserDir) {
    unless (mkdir($vncUserDir, 0700)) {
        die "$prog: Could not create $vncUserDir.\n";
    }
}
($z,$z,$mode) = stat("$vncUserDir");
if (!-d _ || !-o _ || ($vncUserDirUnderTmp && ($mode & 0777) != 0700)) {
    die "$prog: Wrong type or access mode of $vncUserDir.\n";
}

# Make sure the user has a password.

($z,$z,$mode) = stat("$vncUserDir/passwd");
if (-e _ && (!-f _ || !-o _)) {
    die "$prog: Wrong type or ownership on $vncUserDir/passwd.\n";
}
if (!-e _ || ($mode & 077) != 0) {
    warn "\nYou will require a password to access your desktops.\n\n";
    system("vncpasswd $vncUserDir/passwd");
    if (($? & 0xFF00) != 0) {
        exit 1;
    }
}

# Find display number.

if ((@ARGV > 0) && ($ARGV[0] =~ /^:(\d+)$/)) {
    $displayNumber = $1;
    shift(@ARGV);
    unless (&CheckDisplayNumber($displayNumber)) {
	die "A VNC server is already running as :$displayNumber\n";
    }
} elsif ((@ARGV > 0) && ($ARGV[0] !~ /^-/)) {
    &Usage();
} else {
    $displayNumber = &GetDisplayNumber();
}

$vncPort = 5900 + $displayNumber;

$desktopLog = "$vncUserDir/$host:$displayNumber.log";
unlink($desktopLog);

# Make an X server cookie - use as the seed the sum of the current time, our
# PID and part of the encrypted form of the password.  Ideally we'd use
# /dev/urandom, but that's only available on Linux.

srand(time+$$+unpack("L",`cat $vncUserDir/passwd`));
$cookie = "";
for (1..16) {
    $cookie .= sprintf("%02x", int(rand(256)));
}

system("xauth -f $xauthorityFile add $host:$displayNumber . $cookie");
system("xauth -f $xauthorityFile add $host/unix:$displayNumber . $cookie"); 

# Now start the X VNC Server

$cmd = "Xtightvnc :$displayNumber";
$cmd .= " -desktop " . &quotedString($desktopName);
if ($useClasses) {
  $cmd .= " -httpd $vncClasses";
  print ("Found $vncClasses for http connections.\n");
  if ($opt{'-httpport'}) {
    $cmd .= " -httpport $opt{'-httpport'}";
    print ("Listening to $opt{'-httpport'} for http connections.\n");
  }
  elsif ($opt{'-basehttpport'}) {
    my $v = $opt{'-basehttpport'} + $displayNumber;
    print ("Listening to $v for http connections.\n");
    $cmd .= " -httpport $v";
  }
}
$cmd .= " -auth $xauthorityFile";
$cmd .= " -geometry $geometry" if ($geometry);
$cmd .= " -depth $depth" if ($depth);
$cmd .= " -pixelformat $pixelformat" if ($pixelformat);
$cmd .= " -rfbwait 120000";
$cmd .= " $authType";
$cmd .= " -rfbport $vncPort";
$cmd .= " -fp $fontPath" if ($fontPath);
$cmd .= " -co $colorPath" if ($colorPath);
$cmd .= " -alwaysshared" if ($opt{'-alwaysshared'});
$cmd .= " -nevershared" if ($opt{'-nevershared'});

foreach $arg (@ARGV) {
    $cmd .= " " . &quotedString($arg);
}
$cmd .= " >> " . &quotedString($desktopLog) . " 2>&1";

# Run $cmd and record the process ID.

$pidFile = "$vncUserDir/$host:$displayNumber.pid";
system("$cmd & echo \$! >$pidFile");

# Give Xtightvnc a chance to start up

sleep(1);
unless (kill 0, `cat $pidFile`) {
    warn "Couldn't start Xtightvnc; trying default font path.\n";
    warn "Please set correct fontPath in the $prog script.\n";
    $cmd =~ s@-fp [^ ]+@@;
    system("$cmd & echo \$! >$pidFile");
    sleep(1);
}
unless (kill 0, `cat $pidFile`) {
    warn "Couldn't start Xtightvnc process.\n\n";
    open(LOG, "<$desktopLog");
    while (<LOG>) { print; }
    close(LOG);
    die "\n";
}

warn "\nNew '$desktopName' desktop is $host:$displayNumber\n\n";

# Create the user's xstartup script if necessary.

unless (-e "$xstartup") {
    warn "Creating default startup script $xstartup\n";
    open(XSTARTUP, ">$xstartup");
    print XSTARTUP $defaultXStartup;
    close(XSTARTUP);
    chmod 0755, "$xstartup";
}

# Run the X startup script.

warn "Starting applications specified in $xstartup\n";
warn "Log file is $desktopLog\n\n";

# If the unix domain socket exists then use that (DISPLAY=:n) otherwise use
# TCP (DISPLAY=host:n)

if (-e "/tmp/.X11-unix/X$displayNumber") {
    $ENV{DISPLAY}= ":$displayNumber";
} else {
    $ENV{DISPLAY}= "$host:$displayNumber";
}
$ENV{VNCDESKTOP}= $desktopName;

system("$xstartup >> " . &quotedString($desktopLog) . " 2>&1 &");

exit;

############################ Debian functions #################################
# I thank Manoj for the code below.
#
# ReadConfigFile reads in a config file and sets variables according to it.
#

sub ReadConfigFile
{
  open(CONFIG, "$Config_file") || return;
  my $lineno = 0;
  while (<CONFIG>) {
      chomp;
      $lineno++;
      s/\#.*//og;
      next if /^\s*$/og;
      $_ .= ";" unless /;\s*$/;
      if (/^\s*([^=]+)\s*=\s*(\S.*)$/o) {
          my $ret = eval "$1=$2";
          if ($@) {
              print STDERR "Error parsing config file $Config_file!\n";
              print STDERR "$lineno:$_\n";
          }
      }
  }
}

sub ReadXFConfigFont
{
  open(CONFIG, "$XFConfigPath") || return;
  my $lineno = 0;
  while (<CONFIG>) {
      chomp;
      $lineno++;
      s/\#.*//og;
      next if /^\s*$/og;
      if (/^\s*FontPath\s*"(\S.*)"\s*$/o) {
          $fontPath .= "," if $fontPath;
          $fontPath .= $1;
      }
  }
}

sub ReadXFConfigColor
{
  open(CONFIG, "$XFConfigPath") || return;
  my $lineno = 0;
  while (<CONFIG> && !$colorPath) {
      chomp;
      $lineno++;
      s/\#.*//og;
      next if /^\s*$/og;
      if (/^\s*RgbPath\s*"(\S.*)"\s*$/o) {
          $colorPath = $1;
      }
  }
}


########## End of debian functions ###########

###############################################################################
#
# CheckGeometryAndDepth simply makes sure that the geometry and depth values
# are sensible.
#

sub CheckGeometryAndDepth
{
    if ($geometry =~ /^(\d+)x(\d+)$/) {
	$width = $1; $height = $2;

	if (($width<1) || ($height<1)) {
	    die "$prog: geometry $geometry is invalid\n";
	}

	while (($width % 4)!=0) {
	    $width = $width + 1;
	}

	while (($height % 2)!=0) {
	    $height = $height + 1;
	}

	$geometry = "${width}x$height";
    } else {
	die "$prog: geometry $geometry is invalid\n";
    }

    if (($depth < 8) || ($depth > 32)) {
	die "Depth must be between 8 and 32\n";
    }
}


#
# GetDisplayNumber gets the lowest available display number.  A display number
# n is taken if something is listening on the VNC server port (5900+n) or the
# X server port (6000+n).
#

sub GetDisplayNumber
{
    foreach $n (1..99) {
	if (&CheckDisplayNumber($n)) {
	    return $n+0; # Bruce Mah's workaround for bug in perl 5.005_02
	}
    }
    
    die "$prog: no free display number on $host.\n";
}


#
# CheckDisplayNumber checks if the given display number is available.  A
# display number n is taken if something is listening on the VNC server port
# (5900+n) or the X server port (6000+n).
#

sub CheckDisplayNumber
{
    local ($n) = @_;

    socket(S, $AF_INET, $SOCK_STREAM, 0) || die "$prog: socket failed: $!\n";
    eval 'setsockopt(S, &SOL_SOCKET, &SO_REUSEADDR, pack("l", 1))';
    #unless (bind(S, pack('S n x12', $AF_INET, 6000 + $n))) {
    unless (bind(S, sockaddr_in(6000 + $n, &INADDR_ANY))) {
	close(S);
	return 0;
    }
    close(S);

    socket(S, $AF_INET, $SOCK_STREAM, 0) || die "$prog: socket failed: $!\n";
    eval 'setsockopt(S, &SOL_SOCKET, &SO_REUSEADDR, pack("l", 1))';
    #unless (bind(S, pack('S n x12', $AF_INET, 5900 + $n))) {
    unless (bind(S, sockaddr_in(5900 + $n, &INADDR_ANY))) {
	close(S);
	return 0;
    }
    close(S);

    if (-e "/tmp/.X$n-lock") {
	warn "\nWarning: $host:$n is taken because of /tmp/.X$n-lock\n";
	warn "Remove this file if there is no X server $host:$n\n";
	return 0;
    }

    if (-e "/tmp/.X11-unix/X$n") {
	warn "\nWarning: $host:$n is taken because of /tmp/.X11-unix/X$n\n";
	warn "Remove this file if there is no X server $host:$n\n";
	return 0;
    }

    return 1;
}


#
# GetXDisplayDefaults uses xdpyinfo to find out the geometry, depth and pixel
# format of the current X display being used.  If successful, it sets the
# options as appropriate so that the X VNC server will use the same settings
# (minus an allowance for window manager decorations on the geometry).  Using
# the same depth and pixel format means that the VNC server won't have to
# translate pixels when the desktop is being viewed on this X display (for
# TrueColor displays anyway).
#

sub GetXDisplayDefaults
{
    local (@lines, @matchlines, $width, $height, $defaultVisualId, $i,
	   $red, $green, $blue);

    $wmDecorationWidth = 4;	# a guess at typical size for window manager
    $wmDecorationHeight = 24;	# decoration size

    return unless (defined($ENV{DISPLAY}));

    @lines = `xdpyinfo 2>/dev/null`;

    return if ($? != 0);

    @matchlines = grep(/dimensions/, @lines);
    if (@matchlines) {
	($width, $height) = ($matchlines[0] =~ /(\d+)x(\d+) pixels/);

	$width -= $wmDecorationWidth;
	$height -= $wmDecorationHeight;

	$geometry = "${width}x$height";
    }

    @matchlines = grep(/default visual id/, @lines);
    if (@matchlines) {
	($defaultVisualId) = ($matchlines[0] =~ /id:\s+(\S+)/);

	for ($i = 0; $i < @lines; $i++) {
	    if ($lines[$i] =~ /^\s*visual id:\s+$defaultVisualId$/) {
		if (($lines[$i+1] !~ /TrueColor/) ||
		    ($lines[$i+2] !~ /depth/) ||
		    ($lines[$i+4] !~ /red, green, blue masks/))
		{
		    return;
		}
		last;
	    }
	}

	return if ($i >= @lines);

	($depth) = ($lines[$i+2] =~ /depth:\s+(\d+)/);
	($red,$green,$blue)
	    = ($lines[$i+4]
	       =~ /masks:\s+0x([0-9a-f]+), 0x([0-9a-f]+), 0x([0-9a-f]+)/);

	$red = hex($red);
	$green = hex($green);
	$blue = hex($blue);

	if ($red > $blue) {
	    $red = int(log($red) / log(2)) - int(log($green) / log(2));
	    $green = int(log($green) / log(2)) - int(log($blue) / log(2));
	    $blue = int(log($blue) / log(2)) + 1;
	    $pixelformat = "rgb$red$green$blue";
	} else {
	    $blue = int(log($blue) / log(2)) - int(log($green) / log(2));
	    $green = int(log($green) / log(2)) - int(log($red) / log(2));
	    $red = int(log($red) / log(2)) + 1;
	    $pixelformat = "bgr$blue$green$red";
	}
    }
}


#
# quotedString returns a string which yields the original string when parsed
# by a shell.
#

sub quotedString
{
    local ($in) = @_;

    $in =~ s/\'/\'\"\'\"\'/g;

    return "'$in'";
}


#
# removeSlashes turns slashes into underscores for use as a file name.
#

sub removeSlashes
{
    local ($in) = @_;

    $in =~ s|/|_|g;

    return "$in";
}


#
# Usage
#

sub Usage
{
    die("TightVNC Server version 1.3.10\n".
	"\n".
	"Usage: $prog [<OPTIONS>] [:<DISPLAY#>]\n".
	"       $prog -kill :<DISPLAY#>\n".
	"\n".
	"<OPTIONS> are Xtightvnc options, or:\n".
	"\n".
	"        -name <DESKTOP-NAME>\n".
	"        -depth <DEPTH>\n".
	"        -geometry <WIDTH>x<HEIGHT>\n".
        "        -httpport number\n".
        "        -basehttpport number\n".
        "        -alwaysshared\n".
        "        -nevershared\n".
	"        -pixelformat rgb<NNN>\n".
	"        -pixelformat bgr<NNN>\n".
	"\n".
	"See vncserver and Xtightvnc manual pages for more information.\n");
}


#
# Kill
#

sub Kill
{
    $opt{'-kill'} =~ s/(:\d+)\.\d+$/$1/; # e.g. turn :1.0 into :1

    if ($opt{'-kill'} =~ /^:\d+$/) {
	$pidFile = "$vncUserDir/$host$opt{'-kill'}.pid";
    } else {
	if ($opt{'-kill'} !~ /^$host:/) {
	    die "\nCan't tell if $opt{'-kill'} is on $host\n".
		"Use -kill :<number> instead\n\n";
	}
	$pidFile = "$vncUserDir/$opt{'-kill'}.pid";
    }

    unless (-r $pidFile) {
	die "\nCan't find file $pidFile\n".
	    "You'll have to kill the Xtightvnc process manually\n\n";
    }

    $SIG{'HUP'} = 'IGNORE';
    chop($pid = `cat $pidFile`);
    warn "Killing Xtightvnc process ID $pid\n";
    system("kill $pid");
    unlink $pidFile;

    ## If option -clean is given, also remove the logfile
    unlink "$vncUserDir/$host$opt{'-kill'}.log" if ($opt{'-clean'});

    exit;
}


#
# ParseOptions takes a list of possible options and a boolean indicating
# whether the option has a value following, and sets up an associative array
# %opt of the values of the options given on the command line. It removes all
# the arguments it uses from @ARGV and returns them in @optArgs.
#

sub ParseOptions
{
    local (@optval) = @_;
    local ($opt, @opts, %valFollows, @newargs);

    while (@optval) {
	$opt = shift(@optval);
	push(@opts,$opt);
	$valFollows{$opt} = shift(@optval);
    }

    @optArgs = ();
    %opt = ();

    arg: while (defined($arg = shift(@ARGV))) {
	foreach $opt (@opts) {
	    if ($arg eq $opt) {
		push(@optArgs, $arg);
		if ($valFollows{$opt}) {
		    if (@ARGV == 0) {
			&Usage();
		    }
		    $opt{$opt} = shift(@ARGV);
		    push(@optArgs, $opt{$opt});
		} else {
		    $opt{$opt} = 1;
		}
		next arg;
	    }
	}
	push(@newargs,$arg);
    }

    @ARGV = @newargs;
}


#
# Routine to make sure we're operating in a sane environment.
#

sub SanityCheck
{
    local ($cmd);

    #
    # Get the program name
    #

    ($prog) = ($0 =~ m|([^/]+)$|);

    #
    # Check we have all the commands we'll need on the path.
    #

 cmd:
    foreach $cmd ("uname","xauth","Xtightvnc","vncpasswd") {
	for (split(/:/,$ENV{PATH})) {
	    if (-x "$_/$cmd") {
		next cmd;
	    }
	}
	die "$prog: couldn't find \"$cmd\" on your PATH.\n";
    }

    #
    # Check the HOME and USER environment variables are both set.
    #

    unless (defined($ENV{HOME})) {
	die "$prog: The HOME environment variable is not set.\n";
    }
    unless (defined($ENV{USER})) {
	die "$prog: The USER environment variable is not set.\n";
    }

    #
    # Find socket constants. 'use Socket' is a perl5-ism, so we wrap it in an
    # eval, and if it fails we try 'require "sys/socket.ph"'.  If this fails,
    # we just guess at the values.  If you find perl moaning here, just
    # hard-code the values of AF_INET and SOCK_STREAM.  You can find these out
    # for your platform by looking in /usr/include/sys/socket.h and related
    # files.
    #

    chop($os = `uname`);
    chop($osrev = `uname -r`);

    eval 'use Socket';
    if ($@) {
	eval 'require "sys/socket.ph"';
	if ($@) {
	    if (($os eq "SunOS") && ($osrev !~ /^4/)) {
		$AF_INET = 2;
		$SOCK_STREAM = 2;
	    } else {
		$AF_INET = 2;
		$SOCK_STREAM = 1;
	    }
	} else {
	    $AF_INET = &AF_INET;
	    $SOCK_STREAM = &SOCK_STREAM;
	}
    } else {
	$AF_INET = &AF_INET;
	$SOCK_STREAM = &SOCK_STREAM;
    }
}

sub ReadConfiguration
{
  my @configurableVariables =
    qw(geometry
       depth
       desktopName
       vncClasses
       vncUserDir
       fontPath
       authType
       colorPath
      );

  if (open CONF, "<$configFile") {
    while (<CONF>) {
      if (/^\s*\$(\w+)\s*=\s*(.*)$/) {
        for my $var (@configurableVariables) {
          if ($1 eq $var) {
            eval $_;
            last;
          }
        }
      }
    }
    close CONF;
  }
}

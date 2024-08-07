#! /usr/bin/perl
# vim: set sw=2 sts=2 ts=8 syn=perl expandtab:
#
# vncserver - wrapper script to start an X VNC server.
#
# Copyright (C) 2004-2017 Joachim Falk <joachim.falk@gmx.de>
# Please report all errors to Joachim Falk and not to OL.
#
# This file is based on a vncserver script provided by:
#
#  Copyright (C) 2004 Ola Lundqvist <opal@debian.org>
#  Copyright (C) 2004 Marcus Brinkmann <Marcus.Brinkmann@ruhr-uni-bochum.de>
#  Copyright (C) 2004 Dirk Eddelbuettel <edd@debian.org>
#  Copyright (C) 2002-2003 RealVNC Ltd.
#  Copyright (C) 1999 AT&T Laboratories Cambridge.  All Rights Reserved.
#  Copyright (C) 1997, 1998 Olivetti & Oracle Research Laboratory
#
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307,
# USA.

package config;

#########################################################################
#
# I thank Manoj for the code below. All errors are mine, though.
#
# readConfigFile reads in a config file and sets variables according to it.
#

sub readConfigFile {
  my ( $ConfigFile ) = @_;
  
  eval { do "$ConfigFile"; };
  if ($@) {
    print STDERR "$PROG: Error parsing config file, $@";
  }
  
#  my $lineno = 0;
#  while (<$cf>) {
#    chomp;
#    $lineno++;
#    s/\#.*//og;
#    next if /^\s*$/og;
#    $_ .= ";" unless /;\s*$/;
#    if (/^\s*([^=]+)\s*=\s*(\S.*)$/o) {
#      my $ret = eval "$1=$2";
#      if ($@) {
#	print STDERR "$PROG: Error parsing config file $ConfigFile at line $lineno!\n";
#      }
#    }
#  }
}

package main;

use strict;
use warnings;
use experimental 'smartmatch';

use File::Path;
use File::Spec;
use File::Basename qw(dirname basename);
use DirHandle;
use File::stat;
use IO::File;
use Socket;
use Getopt::Long;
use Time::HiRes qw(usleep);
use Errno qw(:POSIX);
use POSIX ":sys_wait_h";

use vars qw($HOST $HOSTFQDN $USER $PROG %CMDS);

#
# Set global constants
#

# Get the program name
$PROG = basename($0);

sub installPackageError {
  my ($package) = @_;
  print STDERR "\tPlease install the $package package, i.e., sudo apt-get install $package.\n";
  exit 1;
}

sub getCommand {
  my ($cmd) = @_;
  return $CMDS{$cmd} if defined $CMDS{$cmd};
  print STDERR "$PROG: Couldn't find \"$cmd\" on your PATH.\n";
  &installPackageError("tigenvnc-common") if $cmd eq 'tigervncpasswd';
  &installPackageError("openssl") if $cmd eq 'openssl';
  &installPackageError("x11-utils") if $cmd eq 'xdpyinfo';
  exit 1;
}

#
# Routine to make sure we're operating in a sane environment.
#
sub sanityCheck {
  # Get install base bin dir
  my $binbase = dirname(File::Spec->rel2abs($0));

  #
  # Check we have all the commands we'll need on the path.
  #
  %CMDS = ();
cmd:
  foreach my $cmd ("hostname","xauth","Xtigervnc") {
    foreach my $dir ($binbase, split(/:/,$ENV{PATH})) {
      my $fqcmd = File::Spec->catfile($dir, $cmd);
      if (-x $fqcmd) {
        $CMDS{$cmd} = $fqcmd;
	next cmd;
      }
    }
    print STDERR "$PROG: Couldn't find \"$cmd\" on your PATH.\n";
    exit 1;
  }
  # These commands are optional.
  foreach my $cmd ("tigervncpasswd", "openssl", "xdpyinfo") {
    foreach my $dir ($binbase, split(/:/,$ENV{PATH})) {
      my $fqcmd = File::Spec->catfile($dir, $cmd);
      if (-x $fqcmd) {
        $CMDS{$cmd} = $fqcmd;
      }
    }
  }
  #
  # Check the HOME environment variable is set
  #
  if (!defined($ENV{HOME})) {
    print STDERR "$PROG: The HOME environment variable is not set.\n";
    exit 1;
  }
}

sub readConfigFile {
  my $options = shift;
  
  # Add aliases of ::config to %$options
  foreach my $key (keys %$options) {
    no strict 'refs';
    *{"config::$key"} = \$options->{$key};
  }
  foreach my $ConfigFile (@_) {
    next unless -f $ConfigFile; 
    config::readConfigFile( $ConfigFile );
  }
#  foreach my $key (keys %$options) {
#    if ( defined $config::{$key} &&
#         defined *{$config::{$key}}{SCALAR} ) {
#      $options->{$key} = ${*{$config::{$key}}{SCALAR}};
#    }
#    print $key, " => ", $options->{$key}, "\n";
#  }
}

sub readXFConfig {
  my $options = shift;
  my ($XFConfigPath) = @_;
  
  my $cf;
  foreach my $path (split(/:/, $XFConfigPath)) {
    last if defined ($cf = IO::File->new( "<$path" ));
  }
  return unless defined $cf;
  my $lineno = 0;
  my ( $fontPath, $colorPath );
  while (<$cf>) {
    chomp;
    $lineno++;
    s/\#.*//og;
    next if /^\s*$/og;
    if (/^\s*FontPath\s*"(\S.*)"\s*$/o) {
      if (defined $fontPath) {
        $fontPath .= ",$1";
      } else {
        $fontPath  = $1;
      }
    }
#   if (/^\s*RgbPath\s*"(\S.*)"\s*$/o) {
#     $colorPath = $1;
#   }
  }
  if (defined $fontPath) {
    my @fontPathElements = split(/\s*,\s*/, $fontPath);
    
    $fontPath = '';
    foreach my $tempFontPath (@fontPathElements) {
      # is font directory or fontserver (xfs) ?
      if ($tempFontPath !~ m{^[^/]*/[^/]*:\d+$}) {
        # font directory
	$tempFontPath =~ s/:unscaled$//; # remove :unscaled
	# is really a font directory ?
	next unless -r "$tempFontPath/fonts.dir"; # skip if not
      }
      $fontPath .= "$tempFontPath,";
    }
    chop $fontPath; # remove last ','
    $options->{'fontPath'}  = $fontPath;
  }
# if (defined $colorPath) {
#   $options->{'colorPath'} = $colorPath;
# }
}

###############################################################################
#
# checkGeometryAndDepth simply makes sure that the geometry and depth values
# are sensible.
#

sub checkGeometryAndDepth {
  my ( $options ) = @_;
  
  my $wmDecorationWidth;
  my $wmDecorationHeight;
  
  if ($options->{'wmDecoration'} =~ /^(\d+)x(\d+)$/) {
    ($wmDecorationWidth, $wmDecorationHeight) = ($1,$2);
  } else {
    print STDERR "$PROG: wmDecoration $options->{'wmDecoration'} is invalid\n";
    exit 1;
  }
  if ($options->{'geometry'} =~ /^(\d+)x(\d+)$/) {
    my ( $width, $height ) = ( $1, $2 );
    if ($options->{'usedXDisplayDefaultsGeometry'}) {
      $width  -= $wmDecorationWidth;
      $height -= $wmDecorationHeight;
    }
    if (($width<1) || ($height<1)) {
      print STDERR "$PROG: geometry $options->{'geometry'} is invalid\n";
      exit 1;
    }
    
    $width  = int(($width +3)/4)*4;
    $height = int(($height+1)/2)*2;
    
    $options->{'geometry'} = "${width}x${height}";
  } else {
    print STDERR "$PROG: geometry $options->{'geometry'} is invalid\n";
    exit 1;
  }

  if ($options->{'pixelformat'}) {
    unless ($options->{'pixelformat'} =~ m/^(?:rgb|bgr)(\d)(\d)(\d)$/) {
      die 'Internal logic error !';
    }
    if (!defined $options->{'depth'}) {
      $options->{'depth'} = $1+$2+$3;
    } elsif ($options->{'depth'} < $1+$2+$3) {
      print STDERR "$PROG: Depth $options->{'depth'} and pixelformat $options->{'pixelformat'} are inconsistent.\n";
      exit 1;
    }
  }
  if (($options->{'depth'} < 8) || ($options->{'depth'} > 32)) {
    print STDERR "$PROG: Depth must be between 8 and 32.\n";
    exit 1;
  }
}

#
# getXDisplayDefaults uses xdpyinfo to find out the geometry, depth and pixel
# format of the current X display being used.  If successful, it sets the
# options as appropriate so that the X VNC server will use the same settings
# (minus an allowance for window manager decorations on the geometry).  Using
# the same depth and pixel format means that the VNC server won't have to
# translate pixels when the desktop is being viewed on this X display (for
# TrueColor displays anyway).
#

sub getXDisplayDefaults {
  my ( $options ) = @_;
  
  my (@lines, @matchlines, $defaultVisualId, $i);
  
  return if !defined($ENV{DISPLAY}) &&
            !defined($options->{'getDefaultFrom'});

  my $xdpyinfo = &getCommand("xdpyinfo");
  if (defined $ENV{DISPLAY}) {
    @lines = `$xdpyinfo 2>/dev/null`;
  } else {
    @lines = `$xdpyinfo $options->{'getDefaultFrom'} 2>/dev/null`;
  }
  
  return if ($? != 0);
  
  @matchlines = grep(/dimensions/, @lines);
  if (@matchlines) {
    my ($width, $height) = ($matchlines[0] =~ /(\d+)x(\d+) pixels/);
    $options->{'geometry'} = "${width}x${height}";
    $options->{'usedXDisplayDefaultsGeometry'} = 1;
  }
  
  @matchlines = grep(/default visual id/, @lines);
  if (@matchlines) {
    ($defaultVisualId) = ($matchlines[0] =~ /id:\s+(\S+)/);

    for ($i = 0; $i < @lines; $i++) {
      if ($lines[$i] =~ /^\s*visual id:\s+$defaultVisualId$/) {
	if (($lines[$i+1] !~ /TrueColor/) ||
	    ($lines[$i+2] !~ /depth/) ||
	    ($lines[$i+4] !~ /red, green, blue masks/)) {
	  return;
	}
	last;
      }
    }

    return if ($i >= @lines);

    ( $options->{'depth'} ) = ($lines[$i+2] =~ /depth:\s+(\d+)/);
    my ($red,$green,$blue)
	= ($lines[$i+4]
	   =~ /masks:\s+0x([0-9a-f]+), 0x([0-9a-f]+), 0x([0-9a-f]+)/);

    $red = hex($red);
    $green = hex($green);
    $blue = hex($blue);

    if ($red > $blue) {
      $red = int(log($red) / log(2)) - int(log($green) / log(2));
      $green = int(log($green) / log(2)) - int(log($blue) / log(2));
      $blue = int(log($blue) / log(2)) + 1;
      $options->{'pixelformat'} = "rgb$red$green$blue";
    } else {
      $blue = int(log($blue) / log(2)) - int(log($green) / log(2));
      $green = int(log($green) / log(2)) - int(log($red) / log(2));
      $red = int(log($red) / log(2)) + 1;
      $options->{'pixelformat'} = "bgr$blue$green$red";
    }
  }
}

#
# Check if tcp port is available
#
sub checkTCPPortUsed {
  my ($port) = @_;
  my $proto  = getprotobyname('tcp');
  
  socket(S, AF_INET, SOCK_STREAM, $proto) || die "$PROG: socket failed: $!";
  setsockopt(S, SOL_SOCKET, SO_REUSEADDR, pack("l", 1)) || die "$PROG: setsockopt failed: $!";
  if (!bind(S, sockaddr_in($port, INADDR_ANY))) {
    # print "$PROG: bind ($port) failed: $!\n";
    close(S);
    return 1;
  }
  close(S);
  return 0;
}

#
# checkDisplayNumberUsed checks if the given display number is used by vnc.
# A display number n is used if something is listening on the X server port
# (6000+n).
#

sub checkDisplayNumberUsed {
  my ($n) = @_;
  return &checkTCPPortUsed( 6000 + $n );
}

#
# checkDisplayNumberAvailable checks if the given display number is available.
# A display number n is taken if something is listening on the X server port
# (6000+n), or if X lock files exist in /tmp.
#

sub checkDisplayNumberAvailable {
  my ($n, $options) = @_;

  return 0 if &checkDisplayNumberUsed($n);

  if (-e "/tmp/.X$n-lock") {
    print "\nWarning: $HOSTFQDN:$n is taken because of /tmp/.X$n-lock\n" unless $options->{'quiet'};
    print "Remove this file if there is no X server $HOSTFQDN:$n\n" unless $options->{'quiet'};
    return 0;
  }

  if (-e "/tmp/.X11-unix/X$n") {
    print "\nWarning: $HOSTFQDN:$n is taken because of /tmp/.X11-unix/X$n\n" unless $options->{'quiet'};
    print "Remove this file if there is no X server $HOSTFQDN:$n\n" unless $options->{'quiet'};
    return 0;
  }
  return 1;
}

#
# getDisplayNumber gets the lowest available display number.  A display number
# n is taken if something is listening on the X server port (6000+n).
#

sub getDisplayNumber {
  my ( $options ) = @_;
  foreach my $n (1..199) {
    return $n if &checkDisplayNumberAvailable($n, $options);
  }
  
  print STDERR "$PROG: no free display number on $HOSTFQDN.\n";
  exit -1;
}

#
# quotedString returns a string which yields the original string when parsed
# by a shell.
#

sub quotedString {
  my ($in) = @_;
  $in =~ s/\'/\'\"\'\"\'/g;
  return "'$in'";
}

sub pidFile {
  my ($options,$usedDisplay) = @_;
  $usedDisplay = $options->{'displayNumber'} unless defined $usedDisplay;
  return "$options->{'vncUserDir'}/$HOSTFQDN:$usedDisplay.pid";
}

sub x509CertFiles {
  my ($options) = @_;
  return (
    "$options->{'vncUserDir'}/${HOSTFQDN}-SrvCert.pem",
    "$options->{'vncUserDir'}/${HOSTFQDN}-SrvKey.pem");
}

sub desktopLog {
  my ($options,$usedDisplay) = @_;
  $usedDisplay = $options->{'displayNumber'} unless defined $usedDisplay;
  return File::Spec->catfile($options->{'vncUserDir'}, "$HOSTFQDN:$usedDisplay.log");
}

sub cleanStale {
  my ($options, $usedDisplay, $stale) = @_;
  my $pidFile  = pidFile($options,$usedDisplay);
  my @x11Locks = ("/tmp/.X$usedDisplay-lock", "/tmp/.X11-unix/X$usedDisplay");
  
  # vnc pidfile stale
  my $msg = "";
  if (-e $pidFile) {
    unless ($options->{'dry-run'} || unlink($pidFile) || $! == &ENOENT) {
      print STDERR "$PROG: Can't clean stale pidfile '$pidFile': $!\n";
    } elsif ($stale) {
      print "Cleaning stale pidfile '$pidFile'!\n" unless $options->{'quiet'};
    }
  }
  if (!$stale || !&checkDisplayNumberUsed($usedDisplay)) {
    foreach my $entry (grep { -e $_ } @x11Locks) {
      unless ($options->{'dry-run'} || unlink($entry) || $! == &ENOENT) {
        print STDERR "$PROG: Can't clean stale x11 lock '$entry': $!\n";
      } else {
        print "Cleaning stale x11 lock '$entry'!\n" unless $options->{'quiet'};
      }
    }
  }
}

sub runningUserVncservers {
  my ($options) = @_;
  my %runningUserVncservers = ();
  
  my $d = DirHandle->new($options->{'vncUserDir'});
  if (defined $d) {
    while (defined(my $entry = $d->read)) {
      next unless $entry =~ m/^\Q$HOSTFQDN\E:(\d+)\.pid$/;
      my $usedDisplay = $1;
      my $pidFile     = File::Spec->catfile($options->{'vncUserDir'}, $entry);
      my $pidFileFh   = IO::File->new($pidFile, "r");
      unless (defined $pidFileFh) {
        print STDERR "$PROG: Can't open pid file '$pidFile': $!\n";
        next;
      }
      unless ($pidFileFh->getline() =~ m/^([0-9]+)$/) {
        print STDERR "$PROG: Can't parse pid file '$pidFile'!\n";
        next;
      }
      my $pid   = int($1);
      my $stale = !kill(0, $pid);
      if ($options->{'cleanstale'} && $stale) {
        cleanStale($options, $usedDisplay, 1);
        next;
      }
      my $DISPLAY = -e "/tmp/.X11-unix/X${usedDisplay}"
        ? ":${usedDisplay}"
	: "$HOSTFQDN:${usedDisplay}";
      # running vnc if !$options->{'cleanstale'}
      $runningUserVncservers{$usedDisplay} = {
          'name'        => "$HOSTFQDN:$usedDisplay",
          'pid'         => $pid,
          'DISPLAY'     => $DISPLAY,
          'usedDisplay' => $usedDisplay,
          'stale'       => $stale,
        };
    }
    undef $d;
  }
  return \%runningUserVncservers;
}

#
# killXvncServer
#

sub killXvncServer {
  my ($options, $runningUserVncservers, $vncs) = @_;
  
  $SIG{'CHLD'} = 'IGNORE';
  my $retval = 0;
  foreach my $vnc (@{$vncs}) {
    my $stale = 0;
    my $pid   = $runningUserVncservers->{$vnc}->{'pid'};
    
    next unless defined $pid;
    print "Killing Xtigervnc process ID $pid..." unless $options->{'quiet'};
    unless ($options->{'dry-run'}) {
      if (kill('TERM', $pid)) {
        my $i = 10;
        for (; $i >= 0; $i = $i-1) {
          last unless kill(0, $pid);
          usleep 100000;
        }
        if ($i >= 0) {
          print " success!\n" unless $options->{'quiet'};
        } else {
          $retval = 1;
          print " which seems to be deadlocked. Using SIGKILL!\n" unless $options->{'quiet'};
          unless (kill('KILL', $pid) || $! == &ESRCH) {
            print STDERR "Can't kill '$pid': $!\n";
            next;
          }
        }
      } elsif ($! == &ESRCH) {
        print " which was already dead\n" unless $options->{'quiet'};
        $stale = 1;
      } else {
        $retval = 1;
        print STDERR "\nCan't kill '$pid': $!\n";
        next;
      }
    }
    &cleanStale($options,$vnc,$stale);
    
    # If option -clean is given, also remove the logfile
    if (!$options->{'dry-run'} && $options->{'clean'}) {
      my $desktopLog = &desktopLog($options, $vnc);
      unless (unlink($desktopLog) || $! == &ENOENT) {
        $retval = 1;
        print STDERR "Can't remove '$desktopLog': $!\n";
      }
    }
  }
  $SIG{'CHLD'} = 'DEFAULT';
  return $retval;
}

sub listXvncServer {
  my ($fh, $options, $runningUserVncservers, $vncs) = @_;
  
  print $fh
    "\n".
    "TigerVNC server sessions:\n".
    "\n".
    "X DISPLAY #\tPROCESS ID\n";
  foreach my $vnc (@{$vncs}) {
    next unless defined $runningUserVncservers->{$vnc};
    my $stale = "";
    $stale = " (stale)" if $runningUserVncservers->{$vnc}->{'stale'};
    my $pid = $runningUserVncservers->{$vnc}->{'pid'};
    print $fh ":".$vnc."\t\t".$pid.$stale."\n";
  }
}

# Make an X server cookie
sub CreateMITCookie {
  my ( $options ) = @_;
  my $displayNumber  = $options->{'displayNumber'};
  my $xauthorityFile = $options->{'xauthorityFile'};
  my $cookie = `mcookie`; # try mcookie
  
  unless (defined $cookie) {
    # mcookie failed => make an X server cookie the old fashioned way
    srand(time+$$+unpack("L",`cat $options->{'vncPasswdFile'}`));
    $cookie = "";
    for (1..16) {
      $cookie .= sprintf("%02x", int(rand(256)));
    }
  } else {
    chomp $cookie;
  }

  #my ($dev,$ino,$mode,$nlink,$uid,$gid,$rdev,$size,
  #    $atime,$mtime,$ctime,$blksize,$blocks)
  #    = stat($xauthorityFile);

  system(getCommand("xauth"), "-f", "$xauthorityFile", "add", "$HOSTFQDN:$displayNumber", ".", "$cookie");
  system(getCommand("xauth"), "-f", "$xauthorityFile", "add", "$HOST/unix:$displayNumber", ".", "$cookie"); 

  # xauth messes with the file permissions; put them back the way they were
  # chmod $mode, $xauthorityFile;
  # chown $uid, $gid, $xauthorityFile;

  # that doesn't work for some reason; put them back the way we want them
  my $gid = getgrnam("bigbluebutton");
  chown -1, $gid, $xauthorityFile;
  chmod 0640, $xauthorityFile;
}

# Make sure the user has a password.
sub CreateVNCPasswd {
  my ( $options ) = @_;

  # Check whether VNC authentication is enabled, and if so, prompt the user to
  # create a VNC password if they don't already have one.
  return if !$options->{'vncAuthEnabled'} ||
             $options->{'passwordArgSpecified'};
  my $vncPasswdFile = $options->{'vncPasswdFile'};
  my $st = stat($vncPasswdFile);
  
  if (!defined($st) || ($st->mode & 077)) {
    print "\nYou will require a password to access your desktops.\n\n";
    unless (unlink($vncPasswdFile) || $! == &ENOENT) {
      print STDERR "Can't remove old vnc passwd file '$vncPasswdFile': $!!\n";
      exit 1;
    }
    system(getCommand("tigervncpasswd"), $vncPasswdFile); 
    exit 1 if (($? >> 8) != 0);
  }
}

# Make sure the user has a x509 certificate.
sub CreateX509Cert {
  my ( $options ) = @_;
  
  # Check whether X509 encryption is enabled, and if so, create
  # a self signed certificate if not already present or specified
  # on the command line.
  return if !$options->{'x509CertRequired'} ||
            defined $options->{'X509Cert'} ||
            defined $options->{'X509Key'};
  ($options->{'X509Cert'}, $options->{'X509Key'}) = 
    &x509CertFiles($options);
  
  my $st = stat($options->{'X509Key'});
  if (!defined($st) || ($st->mode & 077) || !-f $options->{'X509Cert'}) {
    print "\nYou will require a certificate to use X509None, X509Vnc, or X509Plain.\n";
    print "I will generate a self signed certificate for you in $options->{'X509Cert'}.\n\n";
    unless (unlink($options->{'X509Cert'}) || $! == &ENOENT) {
      print STDERR "Can't remove old X509Cert file '$options->{'X509Cert'}': $!!\n";
      exit 1;
    }
    unless (unlink($options->{'X509Key'}) || $! == &ENOENT) {
      print STDERR "Can't remove old X509Key file '$options->{'X509Key'}': $!!\n";
      exit 1;
    }
    my $toSSLFh;
    my @CMD = split(/\s+/, $options->{'sslAutoGenCertCommand'});
    $CMD[0] = &getCommand($CMD[0]);
    push @CMD, "-config", "-" unless grep { $_ eq "-config" } @CMD;
    push @CMD, "-out", $options->{'X509Cert'} unless grep { $_ eq "-out" } @CMD;
    push @CMD, "-keyout", $options->{'X509Key'} unless grep { $_ eq "-keyout" } @CMD;
    unless (defined open($toSSLFh, "|-", @CMD)) {
      print STDERR "Can't start openssl pipe: $!!\n";
      exit 1;
    }
    my $configSSLFh;
    unless (defined open($configSSLFh, "<", "/etc/tigervnc/ssleay.cnf")) {
      print STDERR "Can't open openssl configuration template /etc/tigervnc/ssleay.cnf: $!\n";
      exit 1;
    }
    while (my $line = <$configSSLFh>) {
      $line =~ s/\@HostName\@/$HOSTFQDN/;
      print $toSSLFh $line;
    }
    close $configSSLFh;
    close $toSSLFh;
    if ($? != 0) {
      unlink $options->{'X509Cert'};
      unlink $options->{'X509Key'};
      print STDERR "The openssl command ", join(' ', @CMD), " failed: $?\n";
      exit 1;
    }
  }
}

# Now start the X VNC Server
sub startXvncServer {
  my ($options) = @_;
  my $vncStartup = $options->{'vncStartup'};
  my $xstartupArg= $options->{'xstartupArgSpecified'};
  my $vncPort    = 5900 + $options->{'displayNumber'};
  my $desktopLog = &desktopLog($options);
  my $pidFile    = &pidFile($options);
  
  # Make sure the user has a password if required.
  &CreateVNCPasswd($options);
  # Make sure the user has a x509 certificate if required.
  &CreateX509Cert($options);
  &CreateMITCookie($options);
  
  # Create the user's vncStartup script if necessary.
  if (defined($vncStartup) && !$xstartupArg && !(-e $vncStartup)) {
    print "Creating default startup script $vncStartup\n" unless $options->{'quiet'};
    unless ($options->{'dry-run'}) {
      my $sf = IO::File->new($vncStartup, "w", 0755);
      unless (defined $sf) {
        print STDERR "$PROG: Can't create startup script '$vncStartup': $!\n";
        exit 1;
      }
      print $sf $options->{'defaultVncStartup'};
      $sf->close;
    }
  }
  if (defined($vncStartup) && !$xstartupArg && !(-x $vncStartup)) {
    unless ($options->{'dry-run'} || chmod 0755, $vncStartup) {
      print STDERR "$PROG: Can't fixup permissions of startup script '$vncStartup': $!\n";
      exit 1;
    }
  }
  
  my $pidFileFh  = IO::File->new($pidFile, "w", 0644);
  unless (defined $pidFileFh) {
    print STDERR "$PROG: Can't create pid file '$pidFile': $!\n";
    exit 1;
  }

  my $xvncServerPid = fork();
  if ($xvncServerPid == 0) {
    # I am the child
    my @cmd = (getCommand("Xtigervnc"));
    push @cmd, ":".$options->{'displayNumber'};
    if (defined $options->{'desktopName'}) {
      push @cmd, '-desktop', $options->{'desktopName'};
    }
    if (defined $options->{'vncClasses'} &&
         (defined($options->{'httpPort'}) ||
          defined($options->{'baseHttpPort'}))) {
      print("Found $options->{'vncClasses'} for http connections.\n") unless $options->{'quiet'};
      push @cmd, '-httpd', $options->{'vncClasses'};
      my $v = $options->{'httpPort'} ||
              $options->{'baseHttpPort'} + $options->{'displayNumber'};
      push @cmd, '-httpPort', $v;
      print("Listening to $v for http connections.\n") unless $options->{'quiet'};
    }
    push @cmd, '-auth', $options->{'xauthorityFile'};
    push @cmd, '-geometry', $options->{'geometry'} if $options->{'geometry'};
    push @cmd, '-depth', $options->{'depth'} if $options->{'depth'};
    push @cmd, '-pixelformat', $options->{'pixelformat'} if $options->{'pixelformat'};
    # The rfbwait option no longer exists (tigervnc 1.12)
    # push @cmd, '-rfbwait', $options->{'rfbwait'};
    push @cmd, '-rfbauth', $options->{'vncPasswdFile'} if $options->{'vncAuthEnabled'};
    push @cmd, '-rfbport', $vncPort;
    push @cmd, '-pn';
    push @cmd, '-localhost' if $options->{'localhost'} =~ m/^(?:yes|true|1)$/i;
    push @cmd, '-fp', $options->{'fontPath'} if $options->{'fontPath'};
    push @cmd, "-SecurityTypes", $options->{'SecurityTypes'} if defined $options->{'SecurityTypes'};
    if ($options->{'plainAuthEnabled'}) {
      push @cmd, "-PAMService", $options->{'PAMService'} if defined $options->{'PAMService'};
      push @cmd, "-PlainUsers", $options->{'PlainUsers'} if defined $options->{'PlainUsers'};
    }
    if ($options->{'x509CertRequired'}) {
      push @cmd, "-X509Cert", $options->{'X509Cert'} if defined $options->{'X509Cert'};
      push @cmd, "-X509Key", $options->{'X509Key'} if defined $options->{'X509Key'};
    }
    push @cmd, @ARGV;

    print join(" ",@cmd), "\n" if $options->{'verbose'};
    open(OLDERR, '>&', \*STDERR); # save old STDERR
    open(STDOUT, '>>', $desktopLog);
    open(STDERR, '>>', $desktopLog);
    STDERR->autoflush(1);
    STDOUT->autoflush(1);
    exec {$cmd[0]} (@cmd) or
      print OLDERR "$PROG: Can't exec '".$cmd[0]."': $!\n";
    exit 1;
  } elsif ($xvncServerPid < 0) {
    # Failed to fork
    print STDERR "$PROG: failed to fork: $!\n";
    exit 1;
  }
  $pidFileFh->print($xvncServerPid."\n");
  $pidFileFh->close();
  
  my $runningUserVncservers = {
      $options->{'displayNumber'} => {
          'name'        => "$HOSTFQDN:".$options->{'displayNumber'},
          'pid'         => $xvncServerPid,
          'usedDisplay' => $options->{'displayNumber'}
        }
    };
  # Wait for Xtigervnc to start up
  {
    my $i = 300;
    # Check for port (5900+n) to be listening unless a UNIX socket was requested
    if (! "-inetd" ~~ @ARGV && ! "-rfbunixpath" ~~ @ARGV) {
      for (; $i >= 0; $i = $i-1) {
        last if &checkTCPPortUsed(5900 + $options->{'displayNumber'});
        if ($xvncServerPid == waitpid($xvncServerPid, WNOHANG)) { $i = -2; last; }
        usleep 100000;
      }
    }
    for (; $i >= 0; $i = $i-1) {
      last if -e "/tmp/.X11-unix/X$options->{'displayNumber'}" ||
              &checkTCPPortUsed(6000 + $options->{'displayNumber'});
      if ($xvncServerPid == waitpid($xvncServerPid, WNOHANG)) { $i = -2; last; }
      usleep 100000;
    }
    if ($i < 0) {
      print STDERR "$PROG: ".getCommand("Xtigervnc")." did not start up, please look into '$desktopLog' to determine the reason! $i\n";
      if (kill(0, $xvncServerPid)) {
        &killXvncServer($options, $runningUserVncservers, [$options->{'displayNumber'}]);
      } else {
        &cleanStale($options,$options->{'displayNumber'},0);
      }
      exit 1;
    }
  }
  # If the unix domain socket exists then use that (DISPLAY=:n) otherwise use
  # TCP (DISPLAY=host:n)
  if (-e "/tmp/.X11-unix/X$options->{'displayNumber'}" ) {
    $ENV{DISPLAY}= ":$options->{'displayNumber'}";
  } else {
    $ENV{DISPLAY}= "$HOSTFQDN:$options->{'displayNumber'}";
  }
  $ENV{VNCDESKTOP} = $options->{'desktopName'};
  print "\nNew '$options->{'desktopName'}' desktop at $ENV{DISPLAY} on machine $HOSTFQDN\n\n"
      unless $options->{'quiet'};

  if (defined $vncStartup) {
    # Run the X startup script.
    print "Starting applications specified in $vncStartup\n" unless $options->{'quiet'};
    print "Log file is $desktopLog\n\n" unless $options->{'quiet'};
  } elsif ($options->{'fg'} || $options->{'autokill'}) {
    # Nothing to start and I should also kill the Xtigervnc server when the
    # Xvnc-session terminates. Well, lets do so. What a pointless exercise.
    &killXvncServer($options, $runningUserVncservers, [$options->{'displayNumber'}]);
  }

  if (kill(0, $xvncServerPid)) {
    my @cmd = ("xtigervncviewer");
    push @cmd, "-SecurityTypes", $options->{'SecurityTypes'};
    push @cmd, "-X509CA", $options->{'X509Cert'} if $options->{'x509CertRequired'};
    push @cmd, "-passwd", $options->{'vncPasswdFile'} if $options->{'vncAuthEnabled'};
    if ($options->{'localhost'} =~ m/^(?:yes|true|1)$/i) {
      push @cmd, ":$options->{'displayNumber'}";
    } else {
      push @cmd, "$HOSTFQDN:$options->{'displayNumber'}";
    }
    print "Use ".join(" ", @cmd)." to connect to the VNC server.\n\n" unless $options->{'quiet'};
  }

  pipe RH, WH or die "Can't open pipe: $!";
  my $childPid = defined $vncStartup
    ? ($options->{'fg'} ? 0 : fork())
    : $$;

  if ($childPid == 0) {
    # I am the child
    my @cmd = ($vncStartup);
    push @cmd, @{$options->{'sessionArgs'}};
    print join(" ",@cmd), "\n" if $options->{'verbose'};

    open(OLDOUT, '>&', \*STDOUT); # save old STDOUT
    open(OLDERR, '>&', \*STDERR); # save old STDERR
    open(STDOUT, '>>', $desktopLog);
    open(STDERR, '>>', $desktopLog);
    STDERR->autoflush(1);
    STDOUT->autoflush(1);
    OLDERR->autoflush(1);
    OLDOUT->autoflush(1);

    $SIG{'ALRM'} = sub {
        open(OLDERR, '>', '/dev/null') unless $options->{'fg'};
        open(OLDOUT, '>', '/dev/null') unless $options->{'fg'};
        syswrite WH, "OK"; close WH;
        $SIG{'ALRM'} = 'DEFAULT';
      };
    # Wait for three seconds for erros to appear and to propagate to
    # our parent if not in -fg mode.
    alarm 3 unless $options->{'fg'};
    $! = 0;
    if (system {$cmd[0]} (@cmd)) {
      if ($!) {
        alarm 0; # this must not be before the if ($!) condition
        print OLDERR "\n$PROG: Can't start ",
          join(" ", map { &quotedString($_); } @cmd), ": $!!\n";
      } else {
        alarm 0; # this must not be before the if ($!) condition
        print OLDERR "\n$PROG: Failed command ",
          join(" ", map { &quotedString($_); } @cmd), ": $?!\n";
      }
      $SIG{'ALRM'} = 'DEFAULT';
      syswrite WH, "ERR"; close WH;
    } else {
      &{$SIG{'ALRM'}} if ref($SIG{'ALRM'}) eq 'CODE';
    }
    if ($options->{'fg'} || $options->{'autokill'}) {
      if (kill(0, $xvncServerPid)) {
        &killXvncServer($options, $runningUserVncservers, [$options->{'displayNumber'}]);
      } else {
        &cleanStale($options,$options->{'displayNumber'},0);
      }
    }
    exit 0 unless $options->{'fg'};
    open(STDOUT, '>&', \*OLDOUT); # restore STDOUT
    open(STDERR, '>&', \*OLDERR); # restore STDERR
  } elsif ($childPid < 0) {
    # Failed to fork
    print STDERR "$PROG: failed to fork: $!\n";
    exit -1;
  }
  if (defined $vncStartup) {
    # I am the parent
    close WH;
    my $status;
    $status = 'ERR' unless defined sysread RH, $status, 3;
    unless ($status eq 'OK') {
      my $header = "=================== tail -15 $desktopLog ===================";
      print STDERR "\n${header}\n";
      system 'tail -15 '.&quotedString($desktopLog).' 1>&2';
      print STDERR "\n".("=" x length $header)."\n\n";
      print STDERR "Starting applications specified in $vncStartup has failed.\n";
      print STDERR "Maybe try something simple first, e.g.,\n";
      print STDERR "\ttigervncserver -xstartup /usr/bin/xterm\n";
      exit -1;
    }
  }
  exit 0;
}

#
# usage
#

sub usage {
  my ($err) = @_;
  
  my $prefix = " " x length("  $PROG ");
  print STDERR "usage:\n".
    "  $PROG -help|-h|-?            This help message. Further help in tigervncserver(1).\n\n".

    "  $PROG [:<number>]            X11 display for VNC server\n".
    $prefix."[-dry-run]             Take no real action\n".
    $prefix."[-verbose]             Be more verbose\n".
    $prefix,"[-quiet]               Be more quiet\n",
    $prefix."[-useold]              Only start VNC server if not already running\n".
    $prefix."[-name <desktop-name>] VNC desktop name\n".
    $prefix."[-depth <depth>]       Desktop bit depth (8|16|24|32)\n".
    $prefix."[-pixelformat          X11 server pixel format\n".
    $prefix."  rgb888|rgb565|rgb332   blue color channel encoded in lower bits\n".
    $prefix." |bgr888|bgr565|bgr233]  red color channel encoded in lower bits\n".
    $prefix."[-geometry <dim>]      Desktop geometry in <width>x<height>\n".
    $prefix."[-xdisplaydefaults]    Get geometry and pixelformat from running X\n".
    $prefix."[-wmDecoration <dim>]  Shrink geometry from xdisplaydefaults by dim\n".
    $prefix."[-localhost yes|no]    Only accept VNC connections from localhost\n".
    $prefix."[-httpPort     port]   Port of internal http server\n".
    $prefix."[-baseHttpPort port]   Calculate http port from base port + display nr\n".
    $prefix."[-fg]                  No daemonization and\n".
    $prefix."                       kill the VNC server after its X session has terminated\n".
    $prefix."[-autokill]            Kill the VNC server after its X session has terminated\n".
    $prefix."[-noxstartup]          Do not run the Xvnc-session script after launching Xtigervnc\n".
    $prefix."[-xstartup]            Specify the script to start after launching Xtigervnc\n".
    $prefix."[-fp fontpath]         Colon separated list of font locations\n".
    $prefix."[-cleanstale]          Do not choke on a stale lockfile\n".
    $prefix."[-SecurityTypes]       Comma list of security types to offer (None, VncAuth,\n".
    $prefix."                       Plain, TLSNone, TLSVnc, TLSPlain, X509None, X509Vnc,\n".
    $prefix."                       X509Plain). On default, offer only VncAuth.\n".
    $prefix."[-PlainUsers]          In case of security types Plain, TLSPlain, and X509Plain,\n".
    $prefix."                       this options specifies the list of authorized users.\n".
    $prefix."[-PAMService]          In case of security types Plain, TLSPlain, and X509Plain,\n".
    $prefix."                       this options specifies the service name for PAM password\n".
    $prefix."                       validation (default vnc if present otherwise tigervnc).\n".
    $prefix."[-PasswordFile]        Password file for security types VncAuth, TLSVnc, and X509Vnc.\n".
    $prefix."                       The default password file is ~/.vnc/passwd\n".
    $prefix."[-passwd]              Alias for PasswordFile\n".
    $prefix."[-rfbauth]             Alias for PasswordFile\n".
    $prefix."[-X509Key]             Path to the key of the X509 certificate in PEM format. This\n".
    $prefix."                       is used by the security types X509None, X509Vnc, and X509Plain.\n".
    $prefix."[-X509Cert]            Path to the X509 certificate in PEM format. This is used by\n".
    $prefix."                       the security types X509None, X509Vnc, and X509Plain.\n".
    $prefix."<X11-options ...>      Further options for Xtigervnc(1)\n".
    $prefix."[-- sessiontype]       Arguments for the VNC startup script Xvnc-session\n\n".

    "  $PROG -kill                  Kill a VNC server\n".
    $prefix."[:<number>|:*]         VNC server to kill, * for all\n".
    $prefix."[-dry-run]             Take no real action\n".
    $prefix."[-verbose]             Be more verbose\n".
    $prefix."[-clean]               Also clean log files of VNC session\n\n".

    "  $PROG -list                  List VNC server sessions\n".
    $prefix."[:<number>|:*]         VNC server to list, * for all\n".
    $prefix."[-cleanstale]          Do not list stale VNC server sessions\n\n";
    
  exit($err ? 1 : 0);
}

sub main {
  #
  # First make sure we're operating in a sane environment.
  #
  &sanityCheck();
  
  # Get the hostname
  {
    my $hostname= getCommand("hostname");
    chomp($HOST     = `$hostname`);
    chomp($HOSTFQDN = `$hostname -f`);
  }
  # Get the username
  chomp($USER = `/usr/bin/id -u -n`);

  #
  # Global options.  You may want to configure some of these for your site.
  # Use /etc/vnc.conf and ~/.vnc/vnc.conf for this purpose.
  #
  my $options = {
# Values that are documented in /etc/vnc.conf
## Values declared as system values in /etc/vnc.conf
      vncClasses		=>
        undef, # /var/www/vnc if the directory exists (checked later)
      baseHttpPort		=> undef,
      XFConfigPath		=> "/etc/X11/xorg.conf",
      fontPath			=> undef,
      PAMService		=>
        undef, # Use vnc if /etc/pam.d/vnc exists. Otherwise,
	       # use our own /etc/pam.d/tigervnc as fallback.
      sslAutoGenCertCommand	=>
      	"openssl req -newkey ec:/etc/tigervnc/ecparams.pem -x509 -days 2190 -nodes",
## Values declared as user values in /etc/vnc.conf, i.e., values
## that are intended to be overwritten by ~/.vnc/vnc.conf.
      vncUserDir		=>
        File::Spec->catfile($ENV{HOME}, ".vnc"),
      vncPasswdFile		=>
        undef, # later derived from vncUserDir
      vncStartup		=>
        undef, # later derived from vncUserDir
      xauthorityFile		=>
        $ENV{XAUTHORITY} ||
        File::Spec->catfile($ENV{HOME}, ".Xauthority"),
      desktopName		=> undef,
      wmDecoration		=>
      	"8x64", # a guess at the typical size for a window manager decoration
      geometry			=> "1280x1024",
      depth			=> 24,
      pixelformat		=> undef,
      getDefaultFrom		=> undef,
      rfbwait			=> 30000,
      localhost			=> undef,
      SecurityTypes		=>
        undef, # later derived depening on localhost setting
      PlainUsers		=>
        undef, # later derived from /usr/bin/id -u -n
      X509Cert			=>
      	undef, # auto generated if absent and stored in
	       # ~/.vnc/${HOSTFQDN}-SrvCert.pem
      X509Key			=>
      	undef, # auto generated if absent and stored in
	       # ~/.vnc/${HOSTFQDN}-SrvKey.pem
# Undocumented values
      defaultVncStartup         => <<SCRIPTEOF
#! /bin/sh

test x"\$SHELL" = x"" && SHELL=/bin/bash
test x"\$1"     = x"" && set -- default

\$SHELL -l <<EOF
exec /etc/X11/Xsession "\$@"
EOF
vncserver -kill \$DISPLAY
SCRIPTEOF
,
      sessionArgs		=> [],
      cleanstale		=> 0,
      clean			=> 0,
      httpPort			=> undef,
      displayNumber		=> undef,
      displayHost		=> undef,
    };
  
  #
  # Then source in configuration files, first the site wide one and then the
  # user specific one.
  #
  {
    my $tmpOpt = { XFConfigPath => $options->{'XFConfigPath'} };
    &readConfigFile($tmpOpt, "/etc/vnc.conf");
    &readXFConfig($options, $tmpOpt->{'XFConfigPath'});
  }
  &readConfigFile($options, "/etc/vnc.conf");
  
  if (!(-d $options->{'vncUserDir'})) {
    # Create the user's vnc directory if necessary.
    if (-e $options->{'vncUserDir'}) {
      print STDERR "$PROG: Could not create $options->{'vncUserDir'}, file exists but is not a directory.\n";
      exit 1;
    }
    if (!mkpath ($options->{'vncUserDir'}, 0, 0755)) {
      print STDERR "$PROG: Could not create $options->{'vncUserDir'}.\n";
      exit 1;
    }
  }
  my $vncStartup = $options->{'vncStartup'};
  undef $options->{'vncStartup'};
  &readConfigFile($options, File::Spec->catfile($options->{'vncUserDir'}, "vnc.conf"));
  unless (defined $options->{'vncStartup'}) {
    # vncStartup was not defined by the user configuration in ~/.vnc/vnc.conf.
    if (-f File::Spec->catfile($options->{'vncUserDir'}, "Xvnc-session")) {
      # A user provided Xvnc-session script exists => user it.
      $options->{'vncStartup'} =
        File::Spec->catfile($options->{'vncUserDir'}, "Xvnc-session");
    } elsif (-f File::Spec->catfile($options->{'vncUserDir'}, "xstartup")) {
      # A user provided Xvnc-session script exists => user it.
      $options->{'vncStartup'} =
        File::Spec->catfile($options->{'vncUserDir'}, "xstartup");
    } elsif (!defined $vncStartup) {
      # vncStartup was not defined by the system configuration in /etc/vnc.conf.
      $options->{'vncStartup'} =
        File::Spec->catfile($options->{'vncUserDir'}, "Xvnc-session");
    } else {
      # Use the system configuration for vncStartup.
      $options->{'vncStartup'} = $vncStartup;
    }
  }
  unless (defined $options->{'vncPasswdFile'}) {
    $options->{'vncPasswdFile'} =
      File::Spec->catfile($options->{'vncUserDir'}, "passwd");
  }
  if (! defined $options->{'vncClasses'}) {
    $options->{'vncClasses'} = "/var/www/vnc" if -d "/var/www/vnc";
  } elsif (! -d $options->{'vncClasses'}) {
    print STDERR "VNC class files can not be found at $options->{'vncClasses'}.";
    exit 1;
  }
  
  {
    # seperate session args
    {
      my @newargv;
      my $ref = \@newargv;
      
      foreach my $entry (@ARGV) {
        if ( $entry eq '--' ) {
          $ref = $options->{'sessionArgs'};
        } else {
          push @$ref, $entry;
        }
      }
      @ARGV = @newargv;
    }

    # Check command line options
    my %opts = (
        kill      => 0,
        help      => 0,
        list      => 0,
        fg        => 0,
        autokill  => 0,
        useold    => 0,
        noxstartup=> 0,
      );
    my $p = new Getopt::Long::Parser;
    $p->configure("pass_through");
    my $rc = $p->getoptions(
      'geometry=s'        => sub {
        $options->{'geometry'} = $_[1];
        $options->{'wmDecoration'} = "0x0"; },
      'depth=i'           => \$options->{'depth'},
      'pixelformat=s'     => sub {
        $options->{'pixelformat'} = $_[1];
        undef $options->{'depth'}; },
      'name=s'            => \$options->{'desktopName'},
      'kill'              => \$opts{'kill'},
      'help|h|?'          => \$opts{'help'},
      'fp=s'              => sub {
        $options->{'fontPath'} = $_[1];
        $opts{'fp'} = $_[1]; },
      'list'              => \$opts{'list'},
      'fg'                => \$opts{'fg'},
      'autokill'          => \$opts{'autokill'},
      'noxstartup'        => \$opts{'noxstartup'},
      'xstartup:s'        => sub {
          $opts{'noxstartup'} = 0;
          if ($_[1] eq '') {
            $opts{'vncStartup'} = undef;
            $opts{'xstartupArgSpecified'} = undef;
          } else {
            $opts{'vncStartup'} = $_[1];
            $opts{'xstartupArgSpecified'} = 1;
          }
        },
      'xdisplaydefaults'  => sub {
        &getXDisplayDefaults($options); },
      'wmDecoration=s'    => \$options->{'wmDecoration'},
      'httpPort=i'        => sub {
        $options->{'httpPort'} = $_[1];
        undef $options->{'baseHttpPort'}; },
      'baseHttpPort=i'    => sub {
        $options->{'baseHttpPort'} = $_[1];
        undef $options->{'httpPort'}; },
      'localhost:s'       =>  sub {
          if ($_[1] eq '') {
            $options->{'localhost'} = 1;
          } else {
            $options->{'localhost'} = $_[1];
          }
        },
      'useold'            => \$opts{'useold'},
      'cleanstale'        => \$options->{'cleanstale'},
      'clean'             => \$options->{'clean'},
      'verbose'           => \$options->{'verbose'},
      'quiet'             => \$opts{'quiet'},
      'dry-run'           => \$options->{'dry-run'},
      'SecurityTypes=s'	  => \$options->{'SecurityTypes'},
      'PAMService=s'	  => \$opts{'PAMService'},
      'PlainUsers=s'	  => \$opts{'PlainUsers'},
      'passwd=s'	  => \$opts{'vncPasswdFile'},
      'rfbauth=s'	  => \$opts{'vncPasswdFile'},
      'PasswordFile=s'	  => \$opts{'vncPasswdFile'},
      'X509Key=s'	  => \$opts{'X509Key'},
      'X509Cert=s'	  => \$opts{'X509Cert'},
      'I-KNOW-THIS-IS-INSECURE' => \$options->{'I-KNOW-THIS-IS-INSECURE'},
    );
    
    &usage(!$rc) if (!$rc || $opts{'help'});
    
    if ((@ARGV > 0) && ($ARGV[0] =~ /^([@\w\d.]*)(?::(\d+(?:\.\d+)?|\*))?$/)) {
      shift(@ARGV);
      $options->{'localhost'} = 'yes' if $1 eq "localhost";
      if (($1 eq "") || ($1 eq "localhost")) {
        $options->{'displayHost'} = $HOSTFQDN;
      } else {
        $options->{'displayHost'} = $1;
      }
      if (defined $2) {
        $options->{'displayNumber'} = $2;
        $options->{'displayNumber'} =~ s{\.\d+$}{};
      }
      if (!$opts{'kill'} && !$opts{'list'}) {
        &usage(1) if ($options->{'displayNumber'}||"") eq '*';
      }
    } elsif ((@ARGV > 0) && ($ARGV[0] !~ /^-/)) {
      &usage(1);
    } else {
      $options->{'displayHost'}   = $HOSTFQDN;
    }
    
    if ($options->{'displayHost'} ne $HOST &&
        $options->{'displayHost'} ne $HOSTFQDN) {
      my @cmdPrefix = ("ssh", "$options->{'displayHost'}", "tigervncserver");
      # Get rid of possible user@ in front of displayHost.
      $options->{'displayHost'} =~ s/^[\w\d.]*@//;
      my @cmd;
      push @cmd, "-dry-run" if $options->{'dry-run'};
      if ( $opts{'kill'} ) {
        push @cmd, "-kill";
        push @cmd, ":$options->{'displayNumber'}" if defined $options->{'displayNumber'};
        push @cmd, "-clean" if ($options->{'clean'});
      } elsif ( $opts{'list'} ) {
        push @cmd, "-list";
        push @cmd, ":$options->{'displayNumber'}" if defined $options->{'displayNumber'};
        push @cmd, "-cleanstale" if ($options->{'cleanstale'});
      } else {
        push @cmd, ":$options->{'displayNumber'}" if defined $options->{'displayNumber'};
        push @cmd, "-geometry", $options->{'geometry'} if ($options->{'geometry'});
        push @cmd, "-pixelformat", $options->{'pixelformat'} if ($options->{'pixelformat'});
        push @cmd, "-depth", $options->{'depth'} if ($options->{'depth'});
        push @cmd, "-name", $options->{'desktopName'} if defined $options->{'desktopName'};
        push @cmd, "-fp", $opts{'fp'} if $opts{'fp'};
        push @cmd, "-fg" if $opts{'fg'};
        push @cmd, "-noxstartup" if $opts{'noxstartup'};
        push @cmd, "-xstartup", $opts{'vncStartup'} if !$opts{'noxstartup'} && defined $opts{'vncStartup'};
        push @cmd, "-autokill" if $opts{'autokill'};
        push @cmd, "-httpPort", $options->{'httpPort'} if ($options->{'httpPort'});
        push @cmd, "-baseHttpPort", $options->{'baseHttpPort'} if ($options->{'baseHttpPort'});
        push @cmd, "-localhost", $options->{'localhost'} if defined $options->{'localhost'};
        push @cmd, "-useold" if $opts{'useold'};
        push @cmd, "-cleanstale" if ($options->{'cleanstale'});
        push @cmd, "-wmDecoration", $options->{'wmDecoration'} if ($options->{'wmDecoration'});
        push @cmd, "-SecurityTypes", $options->{'SecurityTypes'} if defined $options->{'SecurityTypes'};
        push @cmd, "-PAMService", $opts{'PAMService'} if defined $opts{'PAMService'};
        push @cmd, "-PlainUsers", $opts{'PlainUsers'} if defined $opts{'PlainUsers'};
        push @cmd, "-PasswordFile", $opts{'vncPasswdFile'} if defined $opts{'vncPasswdFile'};
        push @cmd, "-X509Key", $opts{'X509Key'} if defined $opts{'X509Key'};
        push @cmd, "-X509Cert", $opts{'X509Cert'} if defined $opts{'X509Cert'};
        push @cmd, @ARGV;
        if ($#{$options->{'sessionArgs'}} >= 0) {
          push @cmd, '--';
          push @cmd, @{$options->{'sessionArgs'}};
        }
      }
      @cmd = (@cmdPrefix, map { &quotedString($_); } @cmd);
      print join(" ",@cmd), "\n" if $options->{'verbose'};
      if (system (@cmd)) {
        print STDERR "\n$PROG: Command '", join(" ", @cmd), "' failed: $?\n";
        exit -1;
      }
      if (!$opts{'kill'} && !$opts{'list'}) {
        # Feedback on how to connect to the remote tigervnc server.
        if (defined $options->{'displayNumber'}) {
          print "Use xtigervncviewer -via $options->{'displayHost'} :$options->{'displayNumber'} to connect!\n"
	      unless $options->{'quiet'};
        } else {
          print "Use xtigervncviewer -via $options->{'displayHost'} :n to connect!\n"
	      unless $options->{'quiet'};
          print "The display number :n is given in the above startup message from tigervncserver.\n"
	      unless $options->{'quiet'};
        }
      }
      exit 0;
    }
    
    unless (defined $options->{'PlainUsers'}) {
      chomp($options->{'PlainUsers'} = `/usr/bin/id -u -n`);
    }
    unless (defined $options->{'PAMService'}) {
      if (-f '/etc/pam.d/vnc') {
        $options->{'PAMService'} = 'vnc';
      } else {
        # Default vnc service not present. Hence, we fall back to our own tigervnc service.
        $options->{'PAMService'} = 'tigervnc';
      }
    }

    foreach my $key (keys %opts) {
      $options->{$key} = $opts{$key} if defined $opts{$key};
    }
    if ($opts{'noxstartup'}) {
      $options->{'vncStartup'} = undef;
      $options->{'xstartupArgSpecified'} = undef;
    }
    if (defined $opts{'vncPasswdFile'}) {
      $options->{'passwordArgSpecified'} = 1;
    } else {
      $options->{'passwordArgSpecified'} = 0;
    }
    if (defined $options->{'localhost'}) {
      $options->{'localhost'} = $options->{'localhost'} =~ m/^(?:yes|true|1)$/i;
    }
    unless (defined $options->{'SecurityTypes'}) {
      if (!defined($options->{'localhost'}) || $options->{'localhost'}) {
        $options->{'SecurityTypes'} = 'VncAuth';
        $options->{'localhost'}     = 1;
      } else {
        $options->{'SecurityTypes'} = 'VncAuth,TLSVnc';
        $options->{'localhost'}     = 0;
      }
    }
    $options->{'vncAuthEnabled'} = 0;
    $options->{'noneAuthEnabled'} = 0;
    $options->{'plainAuthEnabled'} = 0;
    $options->{'x509CertRequired'} = 0;
    $options->{'haveSSLEncryption'} = 0;
    foreach my $securityType (split(',', $options->{'SecurityTypes'})) {
      $options->{'vncAuthEnabled'} = 1    if $securityType =~ m/^(?:.*vnc|vncauth)$/i;
      $options->{'noneAuthEnabled'} = 1   if $securityType =~ m/none$/i;
      $options->{'plainAuthEnabled'} = 1  if $securityType =~ m/plain$/i;
      $options->{'x509CertRequired'} = 1  if $securityType =~ m/^x509/i;
      $options->{'haveSSLEncryption'} = 1 if $securityType =~ m/^(?:x509|tls)/i;
    }

    if ($options->{'plainAuthEnabled'} &&
        $options->{'PAMService'} eq 'tigervnc' &&
        ! -f '/etc/pam.d/tigervnc') {
      print STDERR "$PROG: The tigervnc PAM servcice required for the security types\n";
      print STDERR "\tPlain, TLSPlain, or X509Plain is not installed.\n";
      &installPackageError("tigervnc-common");
    }

    unless (defined $options->{'localhost'}) {
      # If we have no encrypted VNC connection security types or
      # we have at least one *None security type in there, then
      # we better only server VNC on localhost to be tunneled via
      # ssh.
      $options->{'localhost'} = !$options->{'haveSSLEncryption'}
                             || $options->{'noneAuthEnabled'};
    }
    # PREVENT THE USER FROM EXPOSING A VNC SESSION WITHOUT AUTHENTICATION
    # TO THE WHOLE INTERNET!!!
    if (!$options->{'localhost'} && $options->{'noneAuthEnabled'} &&
        !$options->{'I-KNOW-THIS-IS-INSECURE'}) {
      print STDERR "$PROG: YOU ARE TRYING TO EXPOSE A VNC SERVER WITHOUT ANY\n";
      print STDERR "AUTHENTICATION TO THE WHOLE INTERNET! I AM REFUSING TO COOPERATE!\n\n";
      print STDERR "If you really want to do that, add the --I-KNOW-THIS-IS-INSECURE option!\n";
      exit -1;
    }
    if ($options->{'noneAuthEnabled'} &&
        !$options->{'I-KNOW-THIS-IS-INSECURE'}) {
      print STDERR "Please be aware that you are exposing your VNC server to all users on the\n";
      print STDERR "local machine. These users can access your server without authentication!\n";
    }
  }
  
  my $runningUserVncservers = &runningUserVncservers($options);
  my @vncs = ();
  if (defined $options->{'displayNumber'}) {
    if ($options->{'displayNumber'} eq '*') {
      push @vncs, sort keys %{$runningUserVncservers};
    } else {
      push @vncs, $options->{'displayNumber'};
    }
  } elsif ($options->{'kill'} || $options->{'useold'}) {
    push @vncs, sort grep { !$runningUserVncservers->{$_}->{'stale'} } keys %{$runningUserVncservers};
    if ($#vncs >= 1) {
      print STDERR "$PROG: This is ambiguous. Multiple vncservers are running for this user!\n";
      &listXvncServer(\*STDERR, $options, $runningUserVncservers, \@vncs);
      exit 1;
    } elsif ($#vncs == -1 && $options->{'kill'}) {
      print STDERR "$PROG: No vncserver running for this user!\n";
      exit 1;
    } elsif ($#vncs == -1 && $options->{'useold'}) {
      # Find display number.
      push @vncs, &getDisplayNumber($options);
    }
  } elsif ($options->{'list'}) {
    push @vncs, sort keys %{$runningUserVncservers};
  } else {
    # Find display number.
    push @vncs, &getDisplayNumber($options);
  }
  
  if ($options->{'kill'}) {
    my $err = &killXvncServer($options, $runningUserVncservers, \@vncs);
    exit($err ? 1 : 0);
  } elsif ($options->{'list'}) {
    &listXvncServer(\*STDOUT, $options, $runningUserVncservers, \@vncs);
    exit 0;
  } else {
    $options->{'displayNumber'} = $vncs[0];
    
    &checkGeometryAndDepth($options);
    my $haveOld =
      $runningUserVncservers->{$options->{'displayNumber'}} &&
      !$runningUserVncservers->{$options->{'displayNumber'}}->{'stale'};
    if (!&checkDisplayNumberAvailable($options->{'displayNumber'}, $options) &&
        !($options->{'useold'} && $haveOld)) {
      print STDERR "A VNC/X11 server is already running as :$options->{'displayNumber'} on machine $HOSTFQDN\n";
      exit 1;
    }
    unless (defined $options->{'desktopName'}) {
      $options->{'desktopName'} = "${HOSTFQDN}:$options->{'displayNumber'} ($USER)";
    }
    if ($options->{'useold'} && $haveOld) {
      my $DISPLAY = $runningUserVncservers->{$options->{'displayNumber'}}->{'DISPLAY'};
      print "\nUsing old '$options->{'desktopName'}' desktop at $DISPLAY on machine $HOSTFQDN\n\n" unless $options->{'quiet'};
    } else {
      if ($runningUserVncservers->{$options->{'displayNumber'}} &&
          $runningUserVncservers->{$options->{'displayNumber'}}->{'stale'}) {
        &cleanStale($options,$options->{'displayNumber'},1);
      }
      &startXvncServer( $options );
    }
  }
}

&main;

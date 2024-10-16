#!/bin/bash -e

############################
### BEGIN DEB-HELPERS.SH ###
############################

#
# Adding service to autostart
# $1 = service name
#
startService() {
  app_name=$1
  if hash systemctl > /dev/null 2>&1 && [ ! -f /.dockerenv ]; then
    # if there no .service or .timer (or any other suffix), it will add .service suffix
    if [[ ! $app_name =~ ^.*\.[a-z]*$ ]]; then
      app_name="$app_name.service"
    fi
    echo "Adding $app_name to autostart using systemd"
    systemctl enable $app_name
    systemctl start $app_name
  elif hash update-rc.d > /dev/null 2>&1 && [ ! -f /.dockerenv ]; then
    echo "Adding $app_name to autostart using update-rc.d"
    update-rc.d $app_name defaults
    service $app_name start
  elif hash chkconfig > /dev/null 2>&1; then
    echo "Adding $app_name to autostart using chkconfig"
    chkconfig --add $app_name
    chkconfig $app_name on
    service $app_name start
  else
    echo "WARNING: Could not add $app_name to autostart: neither update-rc nor chkconfig found!"
  fi
}

#
# Removing service from autostart
# $1 = service name
#
stopService() {
  app_name=$1
  if hash systemctl > /dev/null 2>&1 && [ ! -f /.dockerenv ]; then
    # if there no .service or .timer (or any other suffix), it will add .service suffix
    if [[ ! $app_name =~ ^.*\.[a-z]*$ ]]; then
      app_name="$app_name.service"
    fi
    echo "Removing $app_name from autostart using systemd"
    if systemctl -q is-active $app_name; then
      systemctl stop $app_name
    fi
    if systemctl is-enabled $app_name > /dev/null 2>&1; then
      systemctl disable $app_name
    fi
  elif hash update-rc.d > /dev/null 2>&1 && [ ! -f /.dockerenv ]; then
    echo "Removing $app_name from autostart using update-rc.d"
    update-rc.d -f $app_name remove
    service $app_name stop
  elif hash chkconfig > /dev/null 2>&1; then
    echo "Removing $app_name from autostart using chkconfig"
    chkconfig $app_name off
    chkconfig --del $app_name
    service $app_name stop
  else
    echo "WARNING: Could not remove $app_name from autostart: neither update-rc nor chkconfig found!"
  fi
}

#
# Reload service
# $1 = service name
#
reloadService() {
  app_name=$1
  if hash systemctl > /dev/null 2>&1 && [ ! -f /.dockerenv ]; then
  # if there no .service or .timer (or any other suffix), it will add .service suffix
    if [[ ! $app_name =~ ^.*\.[a-z]*$ ]]; then
      app_name="$app_name.service"
    fi
    echo "Reloading $app_name using systemd"
    if systemctl status $app_name > /dev/null 2>&1; then
      systemctl reload-or-restart $app_name
    else
      startService $app_name
    fi
  elif hash service > /dev/null 2>&1; then
    echo "Reloading $app_name using service"
    service $app_name reload
  else
    echo "WARNING: Could not reload $app_name: neither update-rc nor chkconfig found!"
  fi
}

#
# Restart service
# $1 = service name
#
restartService() {
  app_name=$1
  if hash systemctl > /dev/null 2>&1 && [ ! -f /.dockerenv ]; then
    # if there no .service or .timer (or any other suffix), it will add .service suffix
    if [[ ! $app_name =~ ^.*\.[a-z]*$ ]]; then
      app_name="$app_name.service"
    fi
    echo "Restart $app_name using systemd"
    if systemctl status $app_name > /dev/null 2>&1; then
      systemctl restart $app_name
    else
      startService $app_name
    fi
  elif hash service > /dev/null 2>&1; then
    echo "Restart $app_name using service"
    service $app_name restart
  else
    echo "WARNING: Could not restart $app_name: neither update-rc nor chkconfig found!"
  fi
}

##########################
### END DEB-HELPERS.SH ###
##########################

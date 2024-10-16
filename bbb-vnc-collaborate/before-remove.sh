#!/bin/bash -e

# Embedded Ruby (ERB) enabled with fpm's --template-scripts option
<%= File.read('../deb-helper.sh') %>

stopService bbb-vnc-collaborate || echo "bbb-vnc-collaborate could not be unregistered or stopped"


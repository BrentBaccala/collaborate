#!/bin/sh

VIEWONLY_VIEWER=~/src/ssvnc-1.0.29/vnc_unixsrc/vncviewer/vncviewer
SCALE=.49

$VIEWONLY_VIEWER -viewonly -geometry +0+0 -scale $SCALE -passwd ~/.vnc/passwd osito:1 &
VIEWER_PIDS=$!
$VIEWONLY_VIEWER -viewonly -geometry -0+0 -scale $SCALE -passwd ~/.vnc/passwd osito:3 &
VIEWER_PIDS="$VIEWER_PIDS $!"

echo $VIEWER_PIDS

while true; do
   result=`~/src/xkey $DISPLAY`
   if [ $result -eq 0 ]; then break; fi
   if [ $result -eq 1 ]; then
       ssvncviewer -fullscreen -escape 'Alt_L' -passwd ~/.vnc/passwd osito:1
   fi
   if [ $result -eq 3 ]; then
       ssvncviewer -fullscreen -escape 'Alt_L' -passwd ~/.vnc/passwd osito:3
   fi
done

kill $VIEWER_PIDS

#!/usr/bin/python3
#
# Set a series of gnome-terminal profiles named '8 pt' through '15 pt'
# to allow the user to easily pick different font sizes.
#
# Also sets the color scheme to be white-on-black.

import subprocess

subprocess.run(['dconf', 'load', '/org/gnome/terminal/'], input="""
[legacy/profiles:/:55309155-8061-44a0-9bf5-77aaab51b48c]
background-color='rgb(0,0,0)'
use-theme-colors=false
visible-name='14 pt'
foreground-color='rgb(255,255,255)'
use-system-font=false
font='Monospace 14'

[legacy/profiles:/:db3c5d64-3c94-4a50-9acf-964df7f7bddd]
background-color='rgb(0,0,0)'
use-theme-colors=false
visible-name='9 pt'
foreground-color='rgb(255,255,255)'
use-system-font=false
font='Monospace 9'

[legacy/profiles:/:c04de59a-a195-42d2-acc3-4b4a353675e1]
background-color='rgb(0,0,0)'
use-theme-colors=false
visible-name='10 pt'
foreground-color='rgb(255,255,255)'
use-system-font=false
font='Monospace 10'

[legacy/profiles:/:b1dcc9dd-5262-4d8d-a863-c897e6d979b9]
background-color='rgb(0,0,0)'
use-theme-colors=false
foreground-color='rgb(255,255,255)'
use-system-font=false
visible-name='12 pt'

[legacy/profiles:/:344094d9-37d1-496b-81c5-aa515e862ca7]
background-color='rgb(0,0,0)'
use-theme-colors=false
visible-name='11 pt'
foreground-color='rgb(255,255,255)'
use-system-font=false
font='Monospace 11'

[legacy/profiles:/:f3e5e18a-cb4e-4aee-9b53-d0251dd9aa36]
background-color='rgb(0,0,0)'
use-theme-colors=false
visible-name='13 pt'
foreground-color='rgb(255,255,255)'
use-system-font=false
font='Monospace 13'

[legacy/profiles:]
list=['b1dcc9dd-5262-4d8d-a863-c897e6d979b9', 'db3c5d64-3c94-4a50-9acf-964df7f7bddd', 'c04de59a-a195-42d2-acc3-4b4a353675e1', '344094d9-37d1-496b-81c5-aa515e862ca7', 'f3e5e18a-cb4e-4aee-9b53-d0251dd9aa36', '55309155-8061-44a0-9bf5-77aaab51b48c', '7e906551-9d87-4ef8-a072-8d14654ce400']

[legacy/profiles:/:7e906551-9d87-4ef8-a072-8d14654ce400]
background-color='rgb(0,0,0)'
use-theme-colors=false
visible-name='15 pt'
foreground-color='rgb(255,255,255)'
use-system-font=false
font='Monospace 15'
""".encode('utf-8'))

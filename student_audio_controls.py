#!/usr/bin/python3


import os

import tkinter as tk

import freeswitch

username = os.environ['USER']

window = tk.Tk()

screen_width = window.winfo_screenwidth()
screen_height = window.winfo_screenheight()

# ImageMagick commands to create this graphics (originally extracted from BBB font file bbb-icons.woff)
#
# convert mute_filled_BigBlueButton.ppm -fill blue -opaque white mute_filled_BigBlueButton_blue.gif

mute_white_logo = tk.PhotoImage(file="/home/baccala/src/osito/mute_filled_BigBlueButton.ppm")
mute_blue_logo = tk.PhotoImage(file="/home/baccala/src/osito/mute_filled_BigBlueButton_blue.gif")
deaf_white_logo = tk.PhotoImage(file="/home/baccala/src/osito/listen_filled_BigBlueButton.ppm")
deaf_blue_logo = tk.PhotoImage(file="/home/baccala/src/osito/listen_filled_BigBlueButton_blue.gif")

mute_button = tk.Label(
    text="MUTE",
    image=mute_white_logo,
    width=150,
    height=150,
    bg="white",
    fg="black",
)

deaf_button = tk.Label(
    text="DEAF",
    image=deaf_white_logo,
    width=150,
    height=150,
    bg="white",
    fg="black",
)

def set_correct_icon_status():
    try:
        if freeswitch.mute_status[freeswitch.freeswitch_ids[username]]:
            mute_button.configure(bg='white')
            mute_button.configure(image=mute_white_logo)
        else:
            mute_button.configure(bg='blue')
            mute_button.configure(image=mute_blue_logo)

        if freeswitch.deaf_status[freeswitch.freeswitch_ids[username]]:
            deaf_button.configure(bg='white')
            deaf_button.configure(image=deaf_white_logo)
        else:
            deaf_button.configure(bg='blue')
            deaf_button.configure(image=deaf_blue_logo)
    except:
        pass

mute_button.pack(side="left")
deaf_button.pack(side="right")

window.geometry("+" + str(int(screen_width/2 - 150)) + "-0")

set_correct_icon_status()

window.mainloop()

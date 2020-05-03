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
hand_white_logo = tk.PhotoImage(file="/home/baccala/src/osito/hand_BigBlueButton.png")
hand_blue_logo = tk.PhotoImage(file="/home/baccala/src/osito/hand_BigBlueButton_blue.png")

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

hand_button = tk.Label(
    text="HAND",
    image=hand_white_logo,
    width=150,
    height=150,
    bg="white",
    fg="black",
)

def set_correct_icon_status():
    freeswitch.get_status()
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
    window.after(250, set_correct_icon_status)

hand_raised = False

def handle_click(event):
    global hand_raised
    hand_raised = ~ hand_raised
    if hand_raised:
        hand_button.configure(bg='blue')
        hand_button.configure(image=hand_blue_logo)
    else:
        hand_button.configure(bg='white')
        hand_button.configure(image=hand_white_logo)

hand_button.bind("<Button-1>", handle_click)

mute_button.pack(side="left")
deaf_button.pack(side="left")
hand_button.pack(side="left")

# Center audio control widget at the bottom of the screen
# window.geometry("+" + str(int(screen_width/2 - 150)) + "-0")

# Put audio control widget at the bottom right of the screen
# window.geometry("-0-0")

# Put audio control widget at the top right of the screen
window.geometry("-0+0")

set_correct_icon_status()

window.mainloop()

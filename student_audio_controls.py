#!/usr/bin/python3

import tkinter as tk

window = tk.Tk()

screen_width = window.winfo_screenwidth()
screen_height = window.winfo_screenheight()

mute_logo = tk.PhotoImage(file="/home/baccala/src/osito/mute_filled_BigBlueButton.ppm")
deaf_logo = tk.PhotoImage(file="/home/baccala/src/osito/listen_filled_BigBlueButton.ppm")

mute_button = tk.Label(
    text="MUTE",
    image=mute_logo,
    width=150,
    height=150,
    bg="white",
    fg="black",
)

deaf_button = tk.Label(
    text="DEAF",
    image=deaf_logo,
    width=150,
    height=150,
    bg="white",
    fg="black",
)

mute_button.pack(side="left")
deaf_button.pack(side="right")

window.geometry("+" + str(int(screen_width/2 - 150)) + "-0")

window.mainloop()

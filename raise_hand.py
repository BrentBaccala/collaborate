#!/usr/bin/python3

import tkinter as tk

window = tk.Tk()

button = tk.Label(
    text="Raise your hand!",
    width=25,
    height=5,
    bg="white",
    fg="black",
)

hand_raised = False

def handle_click(event):
    global hand_raised
    hand_raised = ~ hand_raised
    if hand_raised:
        button.configure(bg='blue')
    else:
        button.configure(bg='white')

button.bind("<Button-1>", handle_click)

button.pack()

window.geometry("-0+0")

window.mainloop()

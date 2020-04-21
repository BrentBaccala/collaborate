#!/usr/bin/python3
#
# Usage: simple_text "Text string" X-COORDINATE Y-COORDINATE
#
# "Text string" is displayed with its upper middle point at (X-COORDINATE, Y-COORDINATE)

import sys
import tkinter as tk

window = tk.Tk()

button = tk.Label(
    text=sys.argv[1],
    bg="cyan",
    fg="black",
)

button.pack()

window.update()

# print(button.winfo_width(), button.winfo_height())

xlocation = int(int(sys.argv[2]) - (button.winfo_width()/2))
ylocation = int(sys.argv[3])
window.geometry("+"+str(xlocation)+"+"+str(ylocation))
window.title(sys.argv[1])

window.mainloop()

#
# Usage: simple_text("Text string", X-COORDINATE, Y-COORDINATE)
#
# "Text string" is displayed with its upper middle point at (X-COORDINATE, Y-COORDINATE)

import sys
import tkinter as tk
import multiprocessing

def simple_text(text, x, y):

    def app():

        window = tk.Tk()

        button = tk.Label(
            master=window,
            text=text,
            bg="cyan",
            fg="black",
        )

        button.pack()

        window.update()

        xlocation = int(int(x) - (button.winfo_width()/2))
        ylocation = int(y)
        window.geometry("+"+str(xlocation)+"+"+str(ylocation))
        window.title(text)

        window.mainloop()

    process = multiprocessing.Process(target = app)
    process.start()
    return process

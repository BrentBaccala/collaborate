#
# Usage: simple_text("Text string", X-COORDINATE, Y-COORDINATE)
#
# "Text string" is displayed with its upper middle point at (X-COORDINATE, Y-COORDINATE)

import sys
import tkinter as tk
import multiprocessing
import signal

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

        # Implementing this function with the multiprocessing module
        # is problematic.  We inherit a lot of state from the parent
        # process, in particular, its signal handlers, which were
        # changed in teacher_desktop(), and I do depend on being able
        # to close this window by sending it SIGTERM.  Maybe it would
        # be best to spawn an entire new Python process to avoid these
        # kinds of problems, i.e, use process.Popen rather than
        # multiprocessing.Process.

        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        window.mainloop()

    process = multiprocessing.Process(target = app)
    process.start()
    return process

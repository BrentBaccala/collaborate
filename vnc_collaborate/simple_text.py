
import tkinter as tk
import multiprocessing
import signal

def simple_text(text, x, y):
    r"""
    simple_text(text, x, y)

    Fork a subprocess to display a text string with its upper middle
    point at (x,y), using the tk toolkit.

    Returns a multiprocessing.Process object that manages the subprocess.
    """
    def app():

        window = tk.Tk()

        button = tk.Label(
            master=window,
            text=text,
            bg="cyan",
            fg="black",
        )

        # We can't use the standard Tk options to center the widget on
        # some coordinate, since the widget occupies the entire window
        # and we're using the X11 window geometry to place the window
        # on the screen.  Therefore, call "update" to compute the
        # geometry of the window (even though this causes the window
        # to appear briefly on the screen in the wrong position)
        # before setting its final position.
        #
        # This is why acd4be was reverted.

        button.pack()

        window.update()

        xlocation = int(int(x) - (button.winfo_width()/2))
        ylocation = int(y)
        window.geometry("+"+str(xlocation)+"+"+str(ylocation))
        window.title(text)

        # Implementing this function with the multiprocessing package
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

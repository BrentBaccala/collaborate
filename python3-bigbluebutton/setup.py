#! /usr/bin/python3

import os
import setuptools
import subprocess

with open("README", "r") as fh:
    long_description = fh.read()

timestamp = subprocess.check_output("git log -n1 --pretty=format:%cd --date=format:%Y%m%dt%H%M%S".split()).strip().decode()

# I used Epoch:3 in all of my bigbluebutton-build stuff; that can only be set in the stdeb.cfg file (and it is)

# use 2.4.9 because that was the last version when I moved this out of the bigbluebutton-build repository

# sic is used because BigBlueButton's capital letters aren't standard version numbers for python3 (uses lowercase letters)
# sic doesn't work; just use lowercase 't'
# version = setuptools.sic("2.4.9+" + timestamp)

version = setuptools.sic("2.4.9+" + timestamp)

setuptools.setup(
    name="bigbluebutton",
    version=version,
    author="Brent Baccala",
    author_email="cosine@freesoft.org",
    description="Big Blue Button API bindings",
    long_description=long_description,
    long_description_content_type="text/plain",
    py_modules=['bigbluebutton'],
    install_requires=['pyjavaproperties'],
    scripts=[
        'bbb-get-meetings',
        'bbb-shared-notes'
    ],
    data_files = [('share/man/man1', [
        'bbb-get-meetings.1',
        'bbb-shared-notes.1',
    ])],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Linux",
    ],
)

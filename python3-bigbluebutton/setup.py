#! /usr/bin/python3

import os
import setuptools
from datetime import datetime

with open("README", "r") as fh:
    long_description = fh.read()

version = os.environ['EPOCH'] + ":" + os.environ['VERSION']

setuptools.setup(
    name="bigbluebutton",
    version=version,
    author="Brent Baccala",
    author_email="cosine@freesoft.org",
    description="Big Blue Button API bindings",
    long_description=long_description,
    long_description_content_type="text/plain",
    py_modules=['bigbluebutton'],
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

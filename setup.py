#! /usr/bin/python3

import setuptools
from datetime import datetime

with open("README.md", "r") as fh:
    long_description = fh.read()

version = "0.0.1.dev" + datetime.now().strftime("%Y%m%d%H%M")

setuptools.setup(
    name="vnc-collaborate",
    version=version,
    author="Brent Baccala",
    author_email="cosine@freesoft.org",
    description="Scripts to facilite VNC remote desktop collaboration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/BrentBaccala/collaborate",
    packages=setuptools.find_packages(),
    package_data={
        "vnc_collaborate": ["tightvncserver.pl", "tigervncserver.pl"],
        "": ["*.ppm", "*.gif", "*.png"],
        "vnc_collaborate.fvwm_configs": ["*"]
    },
    install_requires=[
        'psutil',
        'pyjavaproperties',
        'pyjwt',
        'importlib_resources; python_version < "3.7"',
        'vncdotool',
        'service_identity'   # this is just here so twisted doesn't print warning messages
    ],
    scripts=['set-gnome-terminal-fonts'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Linux",
    ],
)

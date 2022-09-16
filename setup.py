#! /usr/bin/python3

import setuptools
import subprocess

with open("README.md", "r") as fh:
    long_description = fh.read()

timestamp = subprocess.check_output("git log -n1 --pretty=format:%cd --date=format:%Y%m%dt%H%M%S".split()).strip().decode()

# sic is used because BigBlueButton's capital letters aren't standard version numbers for python3 (uses lowercase letters)
# sic doesn't work; just use lowercase 't'
# version = setuptools.sic("0.0.2+" + timestamp)
version = setuptools.sic("0.0.2+" + timestamp)

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
        'bigbluebutton',
        'websockify',
        'posix_ipc',
        'psutil',
        'importlib_resources; python_version < "3.7"',
        'vncdotool',
        'pymongo',
        'service_identity'   # this is just here so twisted doesn't print warning messages
    ],
    scripts=[
        'scripts/set-gnome-terminal-fonts',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Linux",
    ],
)

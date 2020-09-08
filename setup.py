#! /usr/bin/python3

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="vnc-collaborate-tool",
    version="0.0.1",
    author="Brent Baccala",
    author_email="cosine@freesoft.org",
    description="Scripts to facilite VNC remote desktop collaboration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/BrentBaccala/collaborate",
    packages=setuptools.find_packages(),
    package_data={
        "": ["*.ppm", "*.gif", "*.png"],
        "vnc_collaborate.fvwm_configs": ["*"]
    },
    install_requires=[
        'pyjavaproperties',
        'importlib_resources; python_version < "3.7"'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Linux",
    ],
)

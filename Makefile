# Chicken-and-egg situation here
#
# We need to install these dependencies because stdeb's algorithm for
# converting python dependencies to dpkg dependencies only works if
# the package is already installed.

DEPENDENCIES=python3-bigbluebutton python3-jwt python3-posix-ipc python3-psutil python3-service-identity python3-vncdotool python3-websockify

all:
	#apt install $(DEPENDENCIES)
	rm -rf deb_dist
	python3 setup.py --command-packages=stdeb.command bdist_deb
	rm vnc-collaborate-*.tar.gz
	rm -r vnc_collaborate.egg-info
	rm -r deb_dist/vnc-collaborate-*/vnc_collaborate.egg-info
	# This is so broken because there's some kind of bug in stdeb that
	# prevents us from including post install scripts.
	#
	# See https://github.com/astraw/stdeb/issues/132
	cp debian/* deb_dist/vnc-collaborate-*/debian/
	cd deb_dist/vnc-collaborate-*; dpkg-buildpackage -rfakeroot -uc -us

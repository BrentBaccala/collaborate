# Chicken-and-egg situation here
#
# We need to install these dependencies because stdeb's algorithm for
# converting python dependencies to dpkg dependencies only works if
# the package is already installed.

DEPENDENCIES=python3-bigbluebutton python3-posix-ipc python3-psutil python3-service-identity python3-vncdotool python3-websockify

collaborate:
	#apt install $(DEPENDENCIES)
	if ! pip3 -q show stdeb; then echo "ERROR: stdeb is required to build python3-vnc-collaborate"; exit 1; fi
	rm -rf deb_dist
	python3 setup.py --command-packages=stdeb.command bdist_deb
	rm vnc-collaborate-*.tar.gz
	rm -r vnc_collaborate.egg-info
	rm -r deb_dist/vnc-collaborate-*/vnc_collaborate.egg-info
	# This is so broken because there's some kind of bug in stdeb that
	# prevents us from including post install scripts.
	#
	# See https://github.com/astraw/stdeb/issues/132
	# cp debian/* deb_dist/vnc-collaborate-*/debian/
	cd deb_dist/vnc-collaborate-*; dpkg-buildpackage -rfakeroot -uc -us
	mkdir -p build
	cp deb_dist/*.deb build

ssvnc:
	mkdir -p build
	cd build; apt source ssvnc
	sed -i 's/do_escape = 1/do_escape = 0/' build/ssvnc*/vnc_unixsrc/vncviewer/desktop.c
	cd build/ssvnc-*; dpkg-buildpackage -b --no-sign

bigbluebutton:
	rm -rf build/bigbluebutton
	mkdir -p build/bigbluebutton
	cd build/bigbluebutton; git init
	cd build/bigbluebutton; git remote add origin https://github.com/BrentBaccala/bigbluebutton.git
	cd build/bigbluebutton; git fetch --depth 1 origin v2.4.x-release
	cd build/bigbluebutton; git checkout v2.4.x-release

bigbluebutton-build:
	# sudo!?  really?  really.  it creates stuff as root
	sudo rm -rf build/bigbluebutton-build
	mkdir -p build/bigbluebutton-build
	cd build/bigbluebutton-build; git init
	# this is a private repository
	#cd build/bigbluebutton-build; git remote add origin https://github.com/BrentBaccala/build.git
	cd build/bigbluebutton-build; git remote add origin git@github.com:BrentBaccala/build.git
	cd build/bigbluebutton-build; git fetch --depth 1 origin master
	cd build/bigbluebutton-build; git checkout master
	# build bbb-vnc-collaborate, python3-bigbluebutton, freesoft-gnome-desktop, bbb-auth-jwt
	cd build/bigbluebutton-build; SOURCE=$(PWD)/build/bigbluebutton PACKAGE=bbb-vnc-collaborate ./setup.sh
	cd build/bigbluebutton-build; SOURCE=$(PWD)/build/bigbluebutton PACKAGE=bbb-auth-jwt ./setup.sh
	cd build/bigbluebutton-build; SOURCE=$(PWD)/build/bigbluebutton PACKAGE=python3-bigbluebutton ./setup.sh
	cd build/bigbluebutton-build; SOURCE=$(PWD)/build/bigbluebutton PACKAGE=freesoft-gnome-desktop ./setup.sh
	cp /tmp/build/*/*.deb build/

vncdotool:
	# sudo apt install python3-sphinx
	# sudo apt install python-sphinx
	# pip3 install pycryptodome
	rm -rf build/vncdotool
	mkdir -p build/vncdotool
	cd build/vncdotool; git init
	cd build/vncdotool; git remote add origin https://github.com/sibson/vncdotool.git
	cd build/vncdotool; git fetch --depth 1 origin v1.0.0
	cd build/vncdotool; git checkout FETCH_HEAD
	# distributed debian/ packaging only builds for python2
	#cd build/vncdotool; dpkg-buildpackage -b --no-sign
	# this will build a python3 package
	cd build/vncdotool; python3 setup.py --command-packages=stdeb.command bdist_deb
	cp build/vncdotool/deb_dist/*.deb build

FORCE: ;

reprepro: FORCE
	mkdir -p bionic-240
	cp -r reprepro bionic-240/conf
	cd bionic-240; http_proxy=http://osito.freesoft.org:3128 reprepro update  # pulls from bigbluebutton.org
	cd bionic-240; reprepro remove bigbluebutton-bionic bbb-html5   # if I want to overwrite without changing filename
	cd bionic-240; reprepro includedeb bigbluebutton-bionic ../build/*.deb
	# rsync -avvz --delete /var/www/html/bionic-230-dev ubuntu@ec2.freesoft.org:/var/www

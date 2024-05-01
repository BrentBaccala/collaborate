# Makefile for the collaborate scripts
#
# Author: Brent Baccala
# Last updated: May 2024
#
# This makefile builds:
#    - the four BigBlueButton packages that need to be changed from a stock 2.4 BigBlueButton system
#       - bbb-html5 is needed for remote desktop support
#       - all four need to be changed for private IP address support, if we're running on a subnetted
#         private network (it works out of the box for a non-subnetted private network)
#       - it checks out my fork of the bigbluebutton repository and calls build/setup.sh for the four packages
#    - two BigBlueButton packages (bbb-vnc-collaborate and freesoft-gnome-desktop) that I build with the old BBB build system
#       - it checks out my private copy of the bigbluebutton-build repository to call setup.sh for each of them
#    - the python3-vnc-collaborate package, built using python setuptools with the stdeb extension
#    - the bbb-vnc-collaborate package, which depends on python3-vnc-collaborate and calls it from systemd scripts
#    - something with pyjavaproperties
#    - a modified ssvnc package; the only change is to disable the escape sequence in the viewer
#    - vncdotool; build from github repository; I think it might be available on PyPi for pip install,
#      but I need a dpkg version to install it as an apt dependency
#    - tigervnc; I think we need 1.10.1 for something and bionic only comes with 1.7.0
#    - bbb-aws-hibernate; optional; only needed to hibernate an AWS system when the server is not in use; built with fpm
#    - bbb-auth-jwt; built with fpm; currently my standard way of authenticating into a collaborate server
#
# Finally, it uses reprepro to pull from the standard bigbluebutton repo, replaces the packages that need to
# be changed, package everything up with reprepro, and export my public key, combined with Fred's to bigbluebutton.asc.

# bash so we can use compgen
SHELL := /bin/bash

# Chicken-and-egg situation here
#
# We need to install these dependencies because stdeb's algorithm for
# converting python dependencies to dpkg dependencies only works if
# the package is already installed.

DEPENDENCIES=python3-bigbluebutton python3-posix-ipc python3-psutil python3-service-identity python3-vncdotool python3-websockify

all: reprepro keys

packages: bigbluebutton bigbluebutton-build collaborate ssvnc vncdotool tigervnc bbb-aws-hibernate bbb-auth-jwt

rsync: all
	rsync -avvz --delete bionic-240 ubuntu@u20.freesoft.org:/var/www/html/

TIMESTAMP := $(shell git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dt%H%M%S')
PYTHON3_VNC_COLLABORATE_PACKAGE=build/python3-vnc-collaborate_0.0.2+$(TIMESTAMP)-1_all.deb
PYTHON3_BIGBLUEBUTTON_PACKAGE=build/python3-bigbluebutton_2.4.9+$(TIMESTAMP)-1_all.deb

collaborate: $(PYTHON3_VNC_COLLABORATE_PACKAGE) $(PYTHON3_BIGBLUEBUTTON_PACKAGE) build/python3-pyjavaproperties_0.7-1_all.deb

$(PYTHON3_VNC_COLLABORATE_PACKAGE):
	#apt install $(DEPENDENCIES)
	if ! pip3 -q show stdeb; then echo "ERROR: stdeb is required to build python3-vnc-collaborate"; exit 1; fi
	# have to remove the old deb_dist, or the setup.py errors out
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
	rm -f build/python3-vnc-collaborate*.deb
	cp deb_dist/*.deb build

$(PYTHON3_BIGBLUEBUTTON_PACKAGE):
	if ! pip3 -q show stdeb; then echo "ERROR: stdeb is required to build python3-bigbluebutton"; exit 1; fi
	# have to remove the old deb_dist, or the setup.py errors out
	rm -rf python3-bigbluebutton/deb_dist
	cd python3-bigbluebutton; python3 setup.py --command-packages=stdeb.command bdist_deb
	rm -f build/python3-bigbluebutton_*.deb
	cp python3-bigbluebutton/deb_dist/*.deb build

build/pyjavaproperties-0.7:
	cd build; wget https://pypi.python.org/packages/source/p/pyjavaproperties/pyjavaproperties-0.7.tar.gz
	cd build; tar xzf pyjavaproperties-0.7.tar.gz

build/python3-pyjavaproperties_0.7-1_all.deb: build/pyjavaproperties-0.7
	cd build/pyjavaproperties-0.7; python3 setup.py --command-packages=stdeb.command bdist_deb
	cp build/pyjavaproperties-0.7/deb_dist/python3-pyjavaproperties_0.7-1_all.deb build
	# without installing it on the system, python3-bigbluebutton's build won't detect it as a dependency
	# sudo dpkg -i build/python3-pyjavaproperties_0.7-1_all.deb

ssvnc: build/ssvnc_1.0.29-3build1_amd64.deb

build/ssvnc_1.0.29-3build1_amd64.deb:
	mkdir -p build
	cd build; apt source ssvnc
	sed -i 's/do_escape = 1/do_escape = 0/' build/ssvnc*/vnc_unixsrc/vncviewer/desktop.c
	cd build/ssvnc-*; dpkg-buildpackage -b --no-sign

# BigBlueButton PACKAGES that need to be custom built for collaborate
#    other BigBlueButton packages are used as distributed by BigBlueButton
#
# bbb-html5 to get remote desktop support
# all four need to be changed for private IP address support

PACKAGES=bbb-html5 bbb-config bbb-freeswitch-core bbb-webrtc-sfu
PLACEHOLDERS=freeswitch bbb-webrtc-sfu

build/bigbluebutton:
	# sudo!?  really?  really.  it creates stuff as root
	sudo rm -rf build/bigbluebutton
	mkdir -p build/bigbluebutton
	cd build/bigbluebutton; git init
	cd build/bigbluebutton; git remote add origin https://github.com/BrentBaccala/bigbluebutton.git

bigbluebutton: build/bigbluebutton
	cd build/bigbluebutton; git fetch --depth 1 origin v2.4.x-release
	cd build/bigbluebutton; git checkout origin/v2.4.x-release
	$(eval BBB_TIMESTAMP := $(shell cd build/bigbluebutton; git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S'))
	cd build/bigbluebutton; for pkg in $(PLACEHOLDERS); do if [ -r $$pkg.placeholder.sh -a ! -r $$pkg ]; then bash $$pkg.placeholder.sh; fi; done
	cd build/bigbluebutton; for pkg in $(PACKAGES); do if ! compgen -G artifacts/$$pkg*$(BBB_TIMESTAMP)*.deb > /dev/null; then ./build/setup.sh $$pkg; rm ../$$pkg*.deb; fi; done
	cp build/bigbluebutton/artifacts/*.deb build/

# BUILD_PACKAGES that I built with the old BigBlueButton build system in a private repository

BUILD_PACKAGES=bbb-vnc-collaborate freesoft-gnome-desktop

build/bigbluebutton-build: build/bigbluebutton
	# sudo!?  really?  really.  it creates stuff as root
	sudo rm -rf build/bigbluebutton-build
	mkdir -p build/bigbluebutton-build
	cd build/bigbluebutton-build; git init
	# this is a private repository
	#cd build/bigbluebutton-build; git remote add origin https://github.com/BrentBaccala/build.git
	cd build/bigbluebutton-build; git remote add origin git@github.com:BrentBaccala/build.git

bigbluebutton-build: build/bigbluebutton build/bigbluebutton-build
	cd build/bigbluebutton-build; git fetch --depth 1 origin master
	cd build/bigbluebutton-build; git checkout origin/master
	# build bbb-vnc-collaborate, python3-bigbluebutton, freesoft-gnome-desktop, bbb-auth-jwt
	$(eval BBB_TIMESTAMP := $(shell cd build/bigbluebutton-build; git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S'))
	cd build/bigbluebutton-build; for pkg in $(BUILD_PACKAGES); do if ! compgen -G ../$$pkg*$(BBB_TIMESTAMP)*.deb > /dev/null; then SOURCE=$(PWD)/build/bigbluebutton PACKAGE=$$pkg ./setup.sh; rm ../$$pkg*.deb; cp /tmp/build/$$pkg/*.deb ..; fi; done


vncdotool: build/python3-vncdotool_1.0.0-1_all.deb

build/python3-vncdotool_1.0.0-1_all.deb:
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

reprepro: packages
	mkdir -p bionic-240/conf
	cp reprepro/* bionic-240/conf/
	cd bionic-240; http_proxy=http://osito.freesoft.org:3128 reprepro update  # pulls from bigbluebutton.org
	cd bionic-240; reprepro remove bigbluebutton-bionic bbb-html5   # if I want to overwrite without changing filename
	cd bionic-240; reprepro includedeb bigbluebutton-bionic ../build/*.deb
	# Don't cache the package lists, but cache the packages themselves (which are in bionic-240/pool)
	# Requires the webserver to be configured to allow overrides in .htaccess files
	echo Header set Cache-Control no-cache > bionic-240/dists/.htaccess

keys: bionic-240/bigbluebutton.asc

bionic-240/bigbluebutton.asc:
	mkdir -p bionic-240
	wget "https://ubuntu.bigbluebutton.org/repo/bigbluebutton.asc" -O bionic-240/fred.asc
	gpg --export --armor --output bionic-240/baccala.asc
	cat bionic-240/fred.asc bionic-240/baccala.asc > bionic-240/bigbluebutton.asc

tigervnc: build/tigervnc-viewer_1.10.1+dfsg-3_amd64.deb build/tigervnc-standalone-server_1.10.1+dfsg-3_amd64.deb

build/tigervnc-viewer_1.10.1+dfsg-3_amd64.deb build/tigervnc-standalone-server_1.10.1+dfsg-3_amd64.deb:
	mkdir -p build
	rm -rf build/tigervnc*
	cd build; wget http://archive.ubuntu.com/ubuntu/pool/universe/t/tigervnc/tigervnc_1.10.1+dfsg-3.dsc
	cd build; wget http://archive.ubuntu.com/ubuntu/pool/universe/t/tigervnc/tigervnc_1.10.1+dfsg.orig.tar.xz
	cd build; wget http://archive.ubuntu.com/ubuntu/pool/universe/t/tigervnc/tigervnc_1.10.1+dfsg-3.debian.tar.xz
	cd build; dpkg-source -x tigervnc_1.10.1+dfsg-3.dsc
	sudo apt install equivs xorg-server-source
	cd build/tigervnc-1.10.1+dfsg; mk-build-deps debian/control
	# ignore xorg-server-source because it wants a newer version
	cd build/tigervnc-1.10.1+dfsg; sudo dpkg -i --ignore-depends=xorg-server-source tigervnc-build-deps*.deb
	sudo apt -y remove tigervnc-build-deps
	# -d to ignore dependency problem with xorg-server-source
	cd build/tigervnc-1.10.1+dfsg; dpkg-buildpackage -d -b --no-sign

bbb-aws-hibernate: build/bbb-aws-hibernate_2.4.9+$(TIMESTAMP)-1_amd64.deb

build/bbb-aws-hibernate_2.4.9+$(TIMESTAMP)-1_amd64.deb: build/bigbluebutton
	if ! which fpm >/dev/null; then echo "ERROR: fpm is required to build bbb-aws-hibernate"; exit 1; fi

	rm -rf build/staging build/staging2

	mkdir -p build/staging/usr/lib/systemd/system
	cp bbb-aws-hibernate/bbb-aws-hibernate.service build/staging/usr/lib/systemd/system

	mkdir -p build/staging/etc/default
	cp bbb-aws-hibernate/bbb-aws-hibernate.default build/staging/etc/default/bbb-aws-hibernate

	mkdir -p build/staging/usr/share/bbb-aws-hibernate
	cp bbb-aws-hibernate/bbb-aws-hibernate build/staging/usr/share/bbb-aws-hibernate

	mkdir -p build/staging2
	cat build/bigbluebutton/build/deb-helper.sh bbb-aws-hibernate/after-install.sh > build/staging2/after-install.sh
	cat build/bigbluebutton/build/deb-helper.sh bbb-aws-hibernate/before-remove.sh > build/staging2/before-remove.sh

	rm -f build/bbb-aws-hibernate*.deb
	fpm -s dir -p build/ -C build/staging -n bbb-aws-hibernate --version 2.4.9+$(TIMESTAMP) --iteration 1 --epoch 3 \
	  --after-install build/staging2/after-install.sh --before-remove build/staging2/before-remove.sh \
	  --description "Automatic hibernation service" \
	  --vendor BigBlueButon -m ffdixon@bigbluebutton.org --url http://bigbluebutton.org/ \
	  -d python3-bigbluebutton,python3-boto3 -t deb

bbb-auth-jwt: build/bbb-auth-jwt_2.4.9+$(TIMESTAMP)-1_amd64.deb

build/bbb-auth-jwt_2.4.9+$(TIMESTAMP)-1_amd64.deb: build/bigbluebutton
	if ! which fpm >/dev/null; then echo "ERROR: fpm is required to build bbb-auth-jwt"; exit 1; fi

	rm -rf build/staging build/staging2

	mkdir -p build/staging/etc/bigbluebutton/nginx
	cp bbb-auth-jwt/auth-jwt.nginx build/staging/etc/bigbluebutton/nginx

	mkdir -p build/staging/usr/lib/systemd/system
	cp bbb-auth-jwt/bbb-auth-jwt.service build/staging/usr/lib/systemd/system

	mkdir -p build/staging/usr/share/bbb-auth-jwt
	cp bbb-auth-jwt/bbb-auth-jwt build/staging/usr/share/bbb-auth-jwt

	mkdir -p build/staging/usr/bin
	cp bbb-auth-jwt/bbb-mklogin build/staging/usr/bin

	mkdir -p build/staging2
	cat build/bigbluebutton/build/deb-helper.sh bbb-auth-jwt/after-install.sh > build/staging2/after-install.sh
	cat build/bigbluebutton/build/deb-helper.sh bbb-auth-jwt/before-remove.sh > build/staging2/before-remove.sh

	rm -f build/bbb-auth-jwt*.deb
	fpm -s dir -p build/ -C build/staging -n bbb-auth-jwt --version 2.4.9+$(TIMESTAMP) --iteration 1 --epoch 3 \
	  --after-install build/staging2/after-install.sh --before-remove build/staging2/before-remove.sh \
	  --description "JSON web token based authentication service for BigBlueButton" \
	  --vendor BigBlueButon -m ffdixon@bigbluebutton.org --url http://bigbluebutton.org/ \
	  --deb-no-default-config-files \
	  -d python3-jwt,python3-dateutil,python3-bigbluebutton,python3-pip -t deb

clean:
	# sudo? there's stuff in build/bigbluebutton and build/bigbluebutton-build that's owned by root
	sudo rm -rf build dist deb_dist bionic-240

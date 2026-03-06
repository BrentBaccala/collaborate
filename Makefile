# Makefile for the collaborate packages
#
# Author: Brent Baccala
# Last updated: March 2026
#
# This makefile builds the server-side packages for BigBlueButton 3.0
# remote desktop collaboration on Ubuntu 22.04 (jammy):
#
#    - bbb-vnc-collaborate — VNC remote desktop service (FPM via build.sh)
#    - python3-vnc-collaborate — Python VNC collaboration module (FPM via build.sh)
#    - python3-bigbluebutton — BBB API bindings (FPM via build.sh)
#    - bbb-auth-jwt — JWT authentication service (FPM)
#    - freesoft-gnome-desktop — GNOME desktop config for VNC (FPM via build.sh)
#    - bbb-wss-proxy — WebSocket proxy (FPM)
#    - bbb-aws-hibernate — AWS auto-hibernate service (FPM)
#    - python3-vncdotool — VNC client tool (not in Ubuntu repos; stdeb from GitHub)
#
# The remote desktop UI is provided by the bbb-plugin-remote-desktop BBB 3.0
# plugin (separate repo). This repo provides the server-side infrastructure.
#
# Uses reprepro to maintain a jammy-300/ apt repository and rsync to publish it.

# bash so we can use compgen
SHELL := /bin/bash

TIMESTAMP := $(shell git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')

all: reprepro keys

packages: bbb-vnc-collaborate python3-vnc-collaborate python3-bigbluebutton bbb-auth-jwt freesoft-gnome-desktop bbb-wss-proxy bbb-aws-hibernate vncdotool dash-to-panel

rsync: all
	rsync -avvz --delete jammy-300 ubuntu@u20.freesoft.org:/var/www/html/

# Packages with their own build.sh scripts

bbb-vnc-collaborate:
	cd bbb-vnc-collaborate && bash build.sh
	mkdir -p build
	rm -f build/bbb-vnc-collaborate*.deb
	cp bbb-vnc-collaborate/bbb-vnc-collaborate*.deb build/

python3-vnc-collaborate:
	cd python3-vnc-collaborate && bash build.sh
	mkdir -p build
	rm -f build/python3-vnc-collaborate*.deb
	cp python3-vnc-collaborate/python3-vnc-collaborate*.deb build/

python3-bigbluebutton:
	cd python3-bigbluebutton && bash build.sh
	mkdir -p build
	rm -f build/python3-bigbluebutton*.deb
	cp python3-bigbluebutton/python3-bigbluebutton*.deb build/

freesoft-gnome-desktop:
	cd freesoft-gnome-desktop && bash build.sh
	mkdir -p build
	rm -f build/freesoft-gnome-desktop*.deb
	cp freesoft-gnome-desktop/freesoft-gnome-desktop*.deb build/

# FPM-built packages

bbb-auth-jwt: build/bbb-auth-jwt_3.0.0+$(TIMESTAMP)-1_amd64.deb

build/bbb-auth-jwt_3.0.0+$(TIMESTAMP)-1_amd64.deb:
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
	cat deb-helper.sh bbb-auth-jwt/after-install.sh > build/staging2/after-install.sh
	cat deb-helper.sh bbb-auth-jwt/before-remove.sh > build/staging2/before-remove.sh

	rm -f build/bbb-auth-jwt*.deb
	fpm -s dir -p build/ -C build/staging -n bbb-auth-jwt --version 3.0.0+$(TIMESTAMP) --iteration 1 --epoch 3 \
	  --after-install build/staging2/after-install.sh --before-remove build/staging2/before-remove.sh \
	  --description "JSON web token based authentication service for BigBlueButton" \
	  --vendor BigBlueButon -m ffdixon@bigbluebutton.org --url http://bigbluebutton.org/ \
	  --deb-no-default-config-files \
	  -d python3-jwt,python3-dateutil,python3-bigbluebutton -t deb

bbb-wss-proxy: build/bbb-wss-proxy_3.0.0+$(TIMESTAMP)-1_all.deb

build/bbb-wss-proxy_3.0.0+$(TIMESTAMP)-1_all.deb:
	if ! which fpm >/dev/null; then echo "ERROR: fpm is required to build bbb-wss-proxy"; exit 1; fi

	rm -rf build/staging build/staging2

	mkdir -p build/staging/etc/bigbluebutton/nginx
	cp bbb-wss-proxy/bbb-wss-proxy.nginx build/staging/etc/bigbluebutton/nginx

	mkdir -p build/staging/usr/lib/systemd/system
	cp bbb-wss-proxy/bbb-wss-proxy.service build/staging/usr/lib/systemd/system

	mkdir -p build/staging/etc/default
	cp bbb-wss-proxy/bbb-wss-proxy.default build/staging/etc/default/bbb-wss-proxy

	mkdir -p build/staging/usr/share/bbb-wss-proxy/bin
	cp bbb-wss-proxy/bbb-wss-proxy build/staging/usr/share/bbb-wss-proxy/bin
	chmod 755 build/staging/usr/share/bbb-wss-proxy/bin/bbb-wss-proxy

	mkdir -p build/staging2
	cat deb-helper.sh bbb-wss-proxy/after-install.sh > build/staging2/after-install.sh
	cat deb-helper.sh bbb-wss-proxy/before-remove.sh > build/staging2/before-remove.sh

	rm -f build/bbb-wss-proxy*.deb
	fpm -s dir -p build/ -C build/staging -n bbb-wss-proxy --version 3.0.0+$(TIMESTAMP) --iteration 1 --epoch 1 \
	  -a all \
	  --after-install build/staging2/after-install.sh --before-remove build/staging2/before-remove.sh \
	  --description "A WebSocket proxy for Big Blue Button" \
	  --vendor BigBlueButon -m "Brent Baccala <cosine@freesoft.org>" --url http://github.com/BrentBaccala/bbb-wss-proxy \
	  --deb-no-default-config-files \
	  -d python3-websockify,python3-jwt -t deb

bbb-aws-hibernate: build/bbb-aws-hibernate_3.0.0+$(TIMESTAMP)-1_amd64.deb

build/bbb-aws-hibernate_3.0.0+$(TIMESTAMP)-1_amd64.deb:
	if ! which fpm >/dev/null; then echo "ERROR: fpm is required to build bbb-aws-hibernate"; exit 1; fi

	rm -rf build/staging build/staging2

	mkdir -p build/staging/usr/lib/systemd/system
	cp bbb-aws-hibernate/bbb-aws-hibernate.service build/staging/usr/lib/systemd/system

	mkdir -p build/staging/etc/default
	cp bbb-aws-hibernate/bbb-aws-hibernate.default build/staging/etc/default/bbb-aws-hibernate

	mkdir -p build/staging/usr/share/bbb-aws-hibernate
	cp bbb-aws-hibernate/bbb-aws-hibernate build/staging/usr/share/bbb-aws-hibernate

	mkdir -p build/staging2
	cat deb-helper.sh bbb-aws-hibernate/after-install.sh > build/staging2/after-install.sh
	cat deb-helper.sh bbb-aws-hibernate/before-remove.sh > build/staging2/before-remove.sh

	rm -f build/bbb-aws-hibernate*.deb
	fpm -s dir -p build/ -C build/staging -n bbb-aws-hibernate --version 3.0.0+$(TIMESTAMP) --iteration 1 --epoch 3 \
	  --after-install build/staging2/after-install.sh --before-remove build/staging2/before-remove.sh \
	  --description "Automatic hibernation service" \
	  --vendor BigBlueButon -m ffdixon@bigbluebutton.org --url http://bigbluebutton.org/ \
	  -d python3-bigbluebutton,python3-boto3,python3-psutil -t deb

# dash-to-panel — download current version from PPA (not in Ubuntu 22.04 repos)

DASH_TO_PANEL_PPA=https://ppa.launchpadcontent.net/gnome-shell-extensions/ppa/ubuntu

dash-to-panel:
	mkdir -p build
	$(eval DTP_PATH := $(shell curl -s $(DASH_TO_PANEL_PPA)/dists/jammy/main/binary-amd64/Packages.gz | \
		zcat | awk '/^Package: gnome-shell-extension-dash-to-panel$$/,/^$$/' | grep '^Filename:' | awk '{print $$2}'))
	@if [ -f build/$(notdir $(DTP_PATH)) ]; then \
		echo "dash-to-panel: build/$(notdir $(DTP_PATH)) is up to date"; \
	else \
		rm -f build/gnome-shell-extension-dash-to-panel*.deb; \
		wget -O build/$(notdir $(DTP_PATH)) $(DASH_TO_PANEL_PPA)/$(DTP_PATH); \
	fi

# vncdotool — not available in Ubuntu repos, build from GitHub with fpm

vncdotool:
	rm -rf build/vncdotool
	mkdir -p build/vncdotool
	cd build/vncdotool && git init
	cd build/vncdotool && git remote add origin https://github.com/sibson/vncdotool.git
	cd build/vncdotool && git fetch --depth 1 origin v1.0.0
	cd build/vncdotool && git checkout FETCH_HEAD
	cd build/vncdotool && python3 setup.py install --root=staging --prefix=/usr --install-layout=deb --no-compile
	rm -f build/python3-vncdotool*.deb
	fpm -s dir -C build/vncdotool/staging -n python3-vncdotool \
	  --version 1.0.0 --iteration 1 \
	  -a all \
	  --description "Command line VNC client" \
	  --vendor freesoft.org -m cosine@freesoft.org --url http://github.com/sibson/vncdotool \
	  --deb-no-default-config-files \
	  -p build/ \
	  -d python3-twisted,python3-pil -t deb

# Repository targets

reprepro: packages
	mkdir -p jammy-300/conf
	cp reprepro/* jammy-300/conf/
	cd jammy-300; for pkg in $$(reprepro list bigbluebutton-jammy 2>/dev/null | awk '{print $$2}' | sort -u); do \
		reprepro remove bigbluebutton-jammy $$pkg; \
	done
	cd jammy-300; reprepro includedeb bigbluebutton-jammy ../build/*.deb
	echo Header set Cache-Control no-cache > jammy-300/dists/.htaccess

keys: jammy-300/freesoft.asc

jammy-300/freesoft.asc:
	mkdir -p jammy-300
	gpg --export --armor --output jammy-300/freesoft.asc

clean:
	rm -rf build dist deb_dist jammy-300
	cd bbb-vnc-collaborate && rm -rf staging *.deb
	cd python3-vnc-collaborate && rm -rf staging *.deb
	cd python3-bigbluebutton && rm -rf staging *.deb
	cd freesoft-gnome-desktop && rm -rf staging *.deb

.PHONY: all packages rsync clean reprepro keys
.PHONY: bbb-vnc-collaborate python3-vnc-collaborate python3-bigbluebutton freesoft-gnome-desktop
.PHONY: bbb-auth-jwt bbb-wss-proxy bbb-aws-hibernate vncdotool dash-to-panel

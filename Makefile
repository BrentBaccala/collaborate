# Makefile for the collaborate packages
#
# Author: Brent Baccala
# Last updated: June 2026
#
# This makefile builds the server-side packages for BigBlueButton 3.0
# remote desktop collaboration on Ubuntu 22.04 (jammy):
#
#    - grid-desktop — systemd unit to bring up a desktop without the user
#                     logging in; installable on a non-BBB host (FPM via build.sh)
#    - bbb-vnc-collaborate — VNC remote desktop service (FPM via build.sh)
#    - python3-vnc-collaborate — Python VNC collaboration module (FPM via build.sh)
#    - python3-bigbluebutton — BBB API bindings (FPM via build.sh)
#    - bbb-auth-jwt — JWT authentication service (FPM)
#    - freesoft-gnome-desktop — GNOME desktop config for VNC (FPM via build.sh)
#    - bbb-aws-hibernate — AWS auto-hibernate service (FPM)
#    - python3-vncdotool — VNC client tool (not in Ubuntu repos; stdeb from GitHub)
#    - bbb-conf-audio — bridge a desktop's audio into a BBB conference as a SIP
#                     participant; system watcher + per-user units (FPM via build.sh)
#    - bbb-vnc-recorder — per-meeting recorder for the collaborate VNC desktops
#                     (FPM via build.sh)
#
# The remote desktop UI is provided by the bbb-plugin-remote-desktop BBB 3.0
# plugin (git submodule).
#
# Uses reprepro to maintain a jammy-300/ apt repository and rsync to publish it.

# bash so we can use compgen
SHELL := /bin/bash

TIMESTAMP := $(shell git log -n1 --pretty='format:%cd' --date=format:'%Y%m%dT%H%M%S')

# The apt repository this Makefile maintains and publishes. It lives under
# ~/website now (formerly ~/collaborate/jammy-300, still a symlink); use this
# variable everywhere so there is a single source of truth for its location.
REPO := $(HOME)/website/jammy-300
CODENAME := bigbluebutton-jammy

# NB: depends on reprepro, so plain `make` inherits its hazard -- see the
# warning on that target.  Do not run this either; publish by hand.
all: reprepro keys

packages: grid-desktop bbb-vnc-collaborate python3-vnc-collaborate python3-bigbluebutton bbb-auth-jwt freesoft-gnome-desktop bbb-aws-hibernate vncdotool dash-to-panel bbb-plugin-remote-desktop bbb-conf-audio bbb-vnc-recorder

# Publish only. Deliberately has NO build prerequisite: the package targets in
# `packages` are phony and rebuild unconditionally (npm/dpkg-buildpackage for
# the plugin, a GitHub fetch for vncdotool, etc.), so chaining `rsync: all`
# rebuilt ~6 packages just to publish an already-current repo.
#
# Build the package, `reprepro includedeb` it into $(REPO) by hand (NOT
# `make reprepro` -- see the warning on that target), then `make rsync` to push
# $(REPO) as-is.  `make status` shows what is built vs what is published.  This
# target is safe: it only mirrors $(REPO), so it publishes exactly what you put
# there.
rsync:
	# No trailing slash on $(REPO): rsync syncs it *into* /var/www/html as
	# the jammy-300/ subdir, so --delete is scoped to /var/www/html/jammy-300/
	# and never touches the rest of the www.freesoft.org docroot.
	rsync -avvz --delete $(REPO) ubuntu@u24.freesoft.org:/var/www/html

# Packages with their own build.sh scripts

grid-desktop:
	cd grid-desktop && bash build.sh
	mkdir -p build
	rm -f build/grid-desktop*.deb
	cp grid-desktop/grid-desktop*.deb build/

bbb-conf-audio:
	cd bbb-conf-audio && bash build.sh
	mkdir -p build
	rm -f build/bbb-conf-audio*.deb
	cp bbb-conf-audio/bbb-conf-audio*.deb build/

# Was published to the apt repo by hand and never wired in here, so `make
# packages` silently skipped it and a `make reprepro` could not refresh it.
bbb-vnc-recorder:
	cd bbb-vnc-recorder && bash build.sh
	mkdir -p build
	rm -f build/bbb-vnc-recorder*.deb
	cp bbb-vnc-recorder/bbb-vnc-recorder*.deb build/

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

	mkdir -p build/staging/etc/networkd-dispatcher/routable.d
	cp bbb-aws-hibernate/50-bbb-aws-hibernate-ddclient build/staging/etc/networkd-dispatcher/routable.d
	chmod 0755 build/staging/etc/networkd-dispatcher/routable.d/50-bbb-aws-hibernate-ddclient

	mkdir -p build/staging2
	cat deb-helper.sh bbb-aws-hibernate/after-install.sh > build/staging2/after-install.sh
	cat deb-helper.sh bbb-aws-hibernate/before-remove.sh > build/staging2/before-remove.sh

	rm -f build/bbb-aws-hibernate*.deb
	fpm -s dir -p build/ -C build/staging -n bbb-aws-hibernate --version 3.0.0+$(TIMESTAMP) --iteration 1 --epoch 3 \
	  --after-install build/staging2/after-install.sh --before-remove build/staging2/before-remove.sh \
	  --description "Automatic hibernation service" \
	  --vendor BigBlueButon -m ffdixon@bigbluebutton.org --url http://bigbluebutton.org/ \
	  -d python3-bigbluebutton,python3-boto3,python3-psutil -t deb

# bbb-plugin-remote-desktop — git submodule, built with dpkg-buildpackage

# dpkg-buildpackage emits both bbb-plugin-remote-desktop and bbb-wss-proxy into
# this directory. Clear old copies first so we don't accumulate stale versions
# (the cp glob would otherwise pick up every past build), and refresh both
# binaries in build/.
bbb-plugin-remote-desktop:
	rm -f bbb-plugin-remote-desktop_*.deb bbb-wss-proxy_*.deb
	cd bbb-plugin-remote-desktop && npm install && npm run build && dpkg-buildpackage -us -uc -b -d
	mkdir -p build
	rm -f build/bbb-plugin-remote-desktop*.deb build/bbb-wss-proxy*.deb
	cp bbb-plugin-remote-desktop_*.deb bbb-wss-proxy_*.deb build/

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

# What is built here vs what is published. Read-only; safe to run any time.
# Run it before and after publishing -- it is the check that would have caught
# build/ drifting two months behind the repo on freesoft-gnome-desktop.
status:
	@bash repo-status.sh

# ##########################################################################
# DO NOT USE `make reprepro`.  Publish one package at a time, by hand:
#
#     cd <pkg> && bash build.sh
#     reprepro -b $(REPO) includedeb $(CODENAME) <pkg>/<pkg>_<version>.deb
#     make rsync
#
# Run `make status` first and after -- it shows, per package, what is built
# here against what is published.
#
# Why not this target: it publishes EVERY .deb sitting in build/, not the
# ones you just built.  build/ is never cleaned between sessions, so it
# accumulates artifacts from packages you are not touching.
#
# It can no longer *downgrade* a published package -- dropping the
# `reprepro remove` restored reprepro's own refusal to go backwards -- but it
# can still publish something you never meant to ship.  Observed 2026-07-25:
# build/ held an unpublished bbb-wss-proxy 0.3.0-16 against the repo's -15,
# so publishing two unrelated packages would have shipped it too.
#
# The `packages` prerequisite makes it worse: it rebuilds all twelve
# packages (npm for the plugin, a GitHub fetch for vncdotool), so a one-line
# fix to one package turns into republishing the whole repo.
#
# Fixing it properly means either cleaning build/ first (which breaks the
# "stage several, publish once" workflow) or passing an explicit package
# list.  Until then, publish by hand.
# ##########################################################################
reprepro: packages
	mkdir -p $(REPO)/conf
	cp reprepro/* $(REPO)/conf/
	# Touch ONLY the packages in build/, leaving anything else already in the
	# repo alone (bbb-plugin-rtt-monitor, vnc-tunnel, libxft*). An older target
	# wiped every package and re-added build/*.deb, which silently dropped those.
	#
	# No `reprepro remove` first, deliberately: reprepro compares versions on
	# includedeb and refuses to go backwards ("Skipping inclusion of 'x' '1.0',
	# as it has already '2.0'"), so a stale .deb in build/ can no longer
	# downgrade a published package. Removing first threw that protection away.
	# The cost is that re-publishing the SAME version with different content is
	# now a no-op -- which is correct, since the rule here is to bump the
	# version on every rebuild. To genuinely replace a version in place, run an
	# explicit `reprepro remove` yourself, as a deliberate act.
	#
	# NB: build/ is still whatever accumulated there, including from earlier
	# sessions -- see the warning above.
	for deb in build/*.deb; do \
		pkg=$$(dpkg-deb -f "$$deb" Package); \
		echo "reprepro: replacing $$pkg"; \
		reprepro -b $(REPO) includedeb $(CODENAME) "$$deb"; \
	done
	echo "Header set Cache-Control no-cache" > $(REPO)/dists/.htaccess

keys: $(REPO)/freesoft.asc

$(REPO)/freesoft.asc:
	mkdir -p $(REPO)
	gpg --export --armor --output $(REPO)/freesoft.asc

# NB: clean removes build artifacts only. It deliberately does NOT touch $(REPO)
# — that is the published apt repository, not a build product.
clean:
	rm -rf build dist deb_dist
	rm -f bbb-plugin-remote-desktop_*.deb bbb-wss-proxy_*.deb *.buildinfo *.changes
	cd bbb-vnc-collaborate && rm -rf staging *.deb
	cd python3-vnc-collaborate && rm -rf staging *.deb
	cd python3-bigbluebutton && rm -rf staging *.deb
	cd freesoft-gnome-desktop && rm -rf staging *.deb

.PHONY: all packages rsync clean reprepro keys status
.PHONY: grid-desktop bbb-vnc-collaborate python3-vnc-collaborate python3-bigbluebutton freesoft-gnome-desktop
.PHONY: bbb-auth-jwt bbb-aws-hibernate vncdotool dash-to-panel bbb-plugin-remote-desktop bbb-conf-audio bbb-vnc-recorder

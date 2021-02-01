# This is so broken because there's some kind of bug in stdeb that
# prevents us from including post install scripts.
#
# See https://github.com/astraw/stdeb/issues/132

all:
	rm -rf deb_dist
	python3 setup.py --command-packages=stdeb.command bdist_deb
	rm vnc-collaborate-tool-*.tar.gz
	rm -r vnc_collaborate_tool.egg-info
	rm -r deb_dist/vnc-collaborate-tool-*/vnc_collaborate_tool.egg-info
	cp python3-vnc-collaborate-tool.* deb_dist/vnc-collaborate-tool-*/debian/
	cd deb_dist/vnc-collaborate-tool-*; dpkg-buildpackage -rfakeroot -uc -us

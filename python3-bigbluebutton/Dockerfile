# Dockerfile to update standard build image by adding the additional
# packages needed to build python3-bigbluebutton
#
# Not strictly necessary - the build.sh script will install these
# packages if they don't exist, but use this Dockerfile to ensure that
# you don't have to re-install the dependencies every time you build
# the package.

FROM ffdixon/build-bionic-h5

RUN apt-get install -y python3-all python3-pip
RUN pip3 install setuptools stdeb

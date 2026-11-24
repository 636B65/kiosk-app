FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:98449306b5efefb0275029a5f09302f863f6a30ab94c5b1c217cea3836d6904f
COPY . $SRC/kiosk-app
WORKDIR $SRC/kiosk-app
COPY .clusterfuzzlite/build.sh $SRC/

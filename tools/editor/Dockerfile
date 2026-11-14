# Pin the last z88dk image whose z88dk-zx0 round-trips; newer images fall back
# to the larger built-in compressor and overflow the demo's ZX Spectrum 48K
# scene budget. Override with --build-arg Z88DK_IMAGE=... to test a newer tree.
ARG Z88DK_IMAGE=z88dk/z88dk:latest@sha256:2922a2a794494fbcb43d56de7022dc898a6bbe6bc2859409d0b00e4be57da9e4
FROM ${Z88DK_IMAGE}

# cc65 supplies the 6502 toolchain for the Commodore 64, NES and Oric Atmos targets
# (z88dk has no C64/NES target). It lives in Alpine's edge/testing repository.
RUN apk add --no-cache \
        --repository https://dl-cdn.alpinelinux.org/alpine/edge/testing cc65=2.19-r0

RUN apk add --no-cache python3 py3-pillow py3-pip m4
# tools/zxart.py needs Pillow; the editor server itself is stdlib-only.
# spectrumizer converts an uploaded MIDI to a .pt3 module for the Music tab;
# the server only spawns its CLI, so it stays stdlib-only.
RUN pip3 install --no-cache-dir --break-system-packages spectrumizer==0.2.2
# The z88dk toolchain is kept so the editor's "Build" button works too.
#
# The project is live-mounted at /src by compose.yml, so this image is just
# the toolchain environment. The build context is only this folder, so the
# repository's models/ (30G), games/ and build outputs are never sent to it.

ENV Z88DK=/opt/z88dk
WORKDIR /src
COPY . /src/tools/editor/

CMD ["python3", "tools/editor/server.py"]

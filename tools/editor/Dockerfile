FROM z88dk/z88dk:latest

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

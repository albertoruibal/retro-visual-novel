"""Strip identifying metadata from generated PNGs and job sidecars.

Image servers such as stable-diffusion.cpp embed a ``tEXt`` chunk with the
generation parameters (and often the model names) in every PNG they return.
Games published from this editor should not carry that metadata, so the
generation paths run the server bytes through :func:`strip_png_metadata`
before writing them. The raw job response is also trimmed by
:func:`sanitize_result` so its ``_result.json`` sidecar cannot name the model.
"""

import struct

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Ancillary chunks that still carry picture data rather than metadata.
_KEEP_ANCILLARY = {b"tRNS"}


def strip_png_metadata(data):
    """Return ``data`` with every non-essential PNG chunk removed.

    Critical chunks (upper-case first letter, e.g. ``IHDR``/``PLTE``/``IDAT``)
    and ``tRNS`` are copied byte-for-byte, so the pixels and transparency are
    unchanged. Text, time, EXIF, colour-profile and other ancillary chunks are
    dropped. Non-PNG input is returned untouched.
    """
    if not data.startswith(_PNG_SIGNATURE):
        return data
    out = bytearray(_PNG_SIGNATURE)
    pos = len(_PNG_SIGNATURE)
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        end = pos + 12 + length
        if end > len(data):
            return data
        ctype = data[pos + 4:pos + 8]
        critical = 0x41 <= ctype[0] <= 0x5A
        if critical or ctype in _KEEP_ANCILLARY:
            out += data[pos:end]
        pos = end
        if ctype == b"IEND":
            break
    return bytes(out)


def sanitize_result(result):
    """Return a job response without the image payload or model details.

    ``images`` repeats the PNGs (including their metadata) and ``info`` carries
    the server's model/backend description, so neither belongs in the ignored
    ``_result.json`` sidecar. Parameters holding base64 image payloads
    (``init_images``/``extra_images``) are dropped too. Everything else is kept
    for debugging.
    """
    out = {k: v for k, v in result.items() if k not in ("images", "info")}
    params = out.get("parameters")
    if isinstance(params, dict):
        out["parameters"] = {k: v for k, v in params.items()
                             if not _is_image_payload(v)}
    return out


def _is_image_payload(value):
    if isinstance(value, str):
        return value.startswith("data:image")
    if isinstance(value, (list, tuple)):
        return any(isinstance(v, str) and v.startswith("data:image")
                   for v in value)
    return False

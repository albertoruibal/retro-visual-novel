"""Locate an installed cc65 toolchain (Commodore 64 and NES targets).

cc65 is the 6502 C toolchain used by the two 6502 build targets.  An explicit
``$CC65``/``$RVN_CC65`` or a saved ``cc65_path`` wins; callers apply that
precedence themselves.  This module answers "where is cc65?" and "which host
tools are present?".
"""
import os
import shutil

BIN_NAMES = ("cl65", "ca65", "ld65", "cc65")
ROOT_CANDIDATES = (
    "/usr",
    "/usr/local",
    "/opt/cc65",
    "/opt/homebrew",
    "/usr/local/opt/cc65",
)


def _exe(name):
    return name + ".exe" if os.name == "nt" else name


def bin_dir(path):
    """The directory holding cc65's binaries for a configured root."""
    path = str(path or "").strip()
    if not path:
        return ""
    if os.path.isfile(path):
        return os.path.dirname(path)
    binp = os.path.join(path, "bin")
    if os.path.isdir(binp):
        return binp
    return path


def looks_like(path):
    """True if ``path`` (a root directory or a binary path) has cl65/ca65."""
    path = str(path or "").strip()
    if not path:
        return False
    bdir = bin_dir(path)
    return os.path.exists(os.path.join(bdir, _exe("cl65"))) and \
        os.path.exists(os.path.join(bdir, _exe("ca65")))


def missing_tools(path=None):
    """Host tools cc65 needs; empty when the install is complete."""
    bdir = bin_dir(path) if path else ""
    if not bdir:
        return [_exe(n) for n in BIN_NAMES]
    return [_exe(n) for n in BIN_NAMES
            if shutil.which(_exe(n), path=bdir) is None]


def detected():
    """The detected cc65 root (or binary directory), or ``""``."""
    for env in ("CC65", "RVN_CC65"):
        value = os.environ.get(env, "").strip()
        if value and looks_like(value):
            return value
    found = shutil.which(_exe("cl65"))
    if found:
        return os.path.dirname(found)
    for root in ROOT_CANDIDATES:
        if looks_like(root):
            return root
    return ""


def available(path=None):
    path = path if path is not None else detected()
    return bool(path) and not missing_tools(path)

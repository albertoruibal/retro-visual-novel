"""Locate an installed z88dk toolchain, including the Ubuntu Snap.

The Snap (`snap install z88dk --beta`) keeps the tree at `/snap/z88dk/current`
(and `/var/lib/snapd/snap/z88dk/current` on systems where `/snap` is not the
mount point). Neither location requires the user to configure a path, so the
editor and the CLI build consult :func:`detected` as their default.

An explicit ``$Z88DK``/``$RVN_Z88DK`` or a saved ``z88dk_path`` still wins;
callers apply that precedence themselves. This module only answers "where is
the Snap tree?" and "what is the default tree?".
"""
import os
import sys

SNAP_ROOTS = ("/snap/z88dk/current",
              "/var/lib/snapd/snap/z88dk/current")


def snap_candidates():
    """Directories where a Snap-installed z88dk may live, best first."""
    if not sys.platform.startswith("linux"):
        return ()
    roots = []
    if os.environ.get("SNAP_NAME") == "z88dk" and os.environ.get("SNAP"):
        roots.append(os.environ["SNAP"])
    roots.extend(SNAP_ROOTS)
    return tuple(roots)


def looks_like(path):
    """True if ``path`` has z88dk's compiler or assembler in ``bin/``."""
    if not path:
        return False
    names = ("zcc.exe", "z88dk-z80asm.exe") if os.name == "nt" \
        else ("zcc", "z88dk-z80asm")
    return any(os.path.exists(os.path.join(path, "bin", name))
               for name in names)


def detected():
    """The detected Snap toolchain root, or ``""`` when none is installed."""
    for root in snap_candidates():
        if looks_like(root):
            return root
    return ""


def default_root():
    """The toolchain used when nothing is configured: Snap, else /tmp/z88dk."""
    return detected() or "/tmp/z88dk"

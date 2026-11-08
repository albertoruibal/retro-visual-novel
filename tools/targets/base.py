"""Shared types for the pluggable build targets.

A target module exports one ``TARGET`` built from these dataclasses.  The
registry (``tools.targets``) discovers modules automatically, so adding a
platform means adding one module plus its generator/engine files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

PORTABLE_CORE = ("state.c", "game.c", "render.c", "inventory.c", "scene.c",
                 "menu.c", "main.c", "music.c")


def portable_sources(root):
    """The shared portable-core C files and header, in build order."""
    base = os.path.join(root, "src", "portable", "core")
    return [os.path.join(base, name) for name in PORTABLE_CORE] + \
           [os.path.join(base, "port.h")]


@dataclass(frozen=True)
class TargetOption:
    """One per-game setting rendered by the editor's Systems card.

    The setting is stored in the target's ``## <id>`` block under ``# Systems`` as
    ``<key>: value`` so a game remains buildable with no editor state. A
    non-empty ``game_key`` stores it as that top-level ``# Game`` setting
    instead (currently ZX ``art_lines``), while still rendering under the
    system. ``kind`` is one of ``choice``, ``int``, ``bool`` or ``text``; a
    ``bool`` may name its on/off spellings with ``on_value``/``off_value``
    (e.g. ``popup``/``inline``) while still rendering as a checkbox.
    """

    key: str
    label: str
    kind: str = "text"
    default: Any = None
    choices: tuple = ()
    help: str = ""
    minimum: int | None = None
    maximum: int | None = None
    game_key: str = ""
    on_value: str = "1"
    off_value: str = "0"


@dataclass
class BuildContext:
    """Everything a target build needs; built by tools/build.py."""

    slug: str
    gdir: str
    doc: dict
    options: dict
    env: dict
    py: str
    root: str
    bdir: str = ""
    verbose: bool = True


@dataclass
class BuildResult:
    """Outcome of one target build."""

    target: str
    outputs: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def add_output(self, path: str, kind: str = "", size: int | None = None) -> None:
        item = {"path": path, "kind": kind}
        if size is not None:
            item["size"] = size
        self.outputs.append(item)


@dataclass(frozen=True)
class Target:
    """A pluggable platform build."""

    id: str
    label: str
    description: str
    outputs: tuple[str, ...]
    build: Callable[[BuildContext], BuildResult | None]
    options: tuple[TargetOption, ...] = ()
    validate: Callable[[BuildContext], Iterable[dict]] | None = None
    preview: Callable[..., Any] | None = None
    available: Callable[[], tuple[bool, str]] | None = None
    emulator: str = ""
    machine: str = ""
    colors: int = 0
    engine: str = ""
    band_width: int = 256
    aliases: tuple[str, ...] = ()
    artifact_suffix: str = ""

    @property
    def option_prefix(self) -> str:
        return self.id + "_"


def option_key(target: Target, option: TargetOption) -> str:
    return target.option_prefix + option.key


def coerce_option(option: TargetOption, raw: Any) -> Any:
    """Parse one stored target option value, falling back to its default."""
    if raw is None or raw == "":
        return option.default
    if option.kind == "int":
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return option.default
        if option.minimum is not None and value < option.minimum:
            return option.default
        if option.maximum is not None and value > option.maximum:
            return option.default
        return value
    if option.kind == "bool":
        if isinstance(raw, bool):
            return raw
        value = str(raw).strip().lower()
        on = str(option.on_value).strip().lower()
        off = str(option.off_value).strip().lower()
        if value in ("1", "true", "on", "yes") or value == on:
            return True
        if value in ("", "0", "false", "off", "no") or value == off:
            return False
        return option.default
    if option.kind == "choice":
        value = str(raw)
        return value if value in tuple(str(c) for c in option.choices) \
            else option.default
    return str(raw)

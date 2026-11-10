"""Target registry: discover pluggable platform builds.

Modules in this package export one ``TARGET`` (see ``base.py``).  The build
driver and the editor both use this registry, so adding a platform is a matter
of dropping a module here; no central target list needs editing.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from .base import (BuildContext, BuildResult, Target, TargetOption,
                   coerce_option, option_key)

__all__ = [
    "BuildContext", "BuildResult", "Target", "TargetOption",
    "all_targets", "get_target", "selected_targets", "ordered_targets",
    "build_separator", "target_options",
    "option_key", "coerce_option", "targets_json", "selection_issues",
]

DISPLAY_ORDER = ("zx128", "zx48", "next", "cpc", "cpc464", "msx2", "c64",
                 "oric", "sms", "nes", "gb")
SEPARATOR_WIDTH = 72

_SKIP = {"__init__", "base", "common"}
_cache: dict[str, Target] | None = None


def _discover() -> dict[str, Target]:
    found: dict[str, Target] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name in _SKIP:
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        target = getattr(mod, "TARGET", None)
        if isinstance(target, Target):
            found[target.id] = target
            for alias in target.aliases:
                found.setdefault(alias, target)
    return found


def all_targets() -> dict[str, Target]:
    global _cache
    if _cache is None:
        _cache = _discover()
    return _cache


def get_target(target_id: str) -> Target | None:
    return all_targets().get(str(target_id or "").strip().lower())


def selected_targets(doc: dict) -> list[str]:
    """The build selection, defaulting to the 128K ZX target for old games."""
    game = (doc or {}).get("game") or {}
    raw = game.get("targets")
    if not raw:
        return ["zx128"]
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    out: list[str] = []
    for name in raw:
        name = str(name).strip().lower()
        target = get_target(name)
        canonical = target.id if target else name
        if canonical and canonical not in out:
            out.append(canonical)
    return out


def ordered_targets(ids: Iterable[str]) -> list[str]:
    """Return canonical target ids in platform display order."""
    out: list[str] = []
    for raw in ids:
        raw_id = str(raw).strip().lower()
        target = get_target(raw_id)
        target_id = target.id if target else raw_id
        if target_id and target_id not in out:
            out.append(target_id)

    def rank(target_id: str) -> int:
        try:
            return DISPLAY_ORDER.index(target_id)
        except ValueError:
            return len(DISPLAY_ORDER)

    return sorted(out, key=rank)


def build_separator(target_id: str, label: str = "") -> str:
    """A banner that clearly separates one target's build log from another."""
    name = f"{label} [{target_id}]" if label else f"[{target_id}]"
    inner = max(1, SEPARATOR_WIDTH - len(name) - 2)
    left = inner // 2
    right = inner - left
    return "=" * left + " " + name + " " + "=" * right


def target_options(doc: dict, target: Target) -> dict:
    game = (doc or {}).get("game") or {}
    extras = game.get("extras") or {}
    out = {}
    for option in target.options:
        if option.game_key:
            raw = game.get(option.game_key)
        else:
            key = option_key(target, option)
            raw = game.get(key, extras.get(key))
            if raw is None:
                for alias in target.aliases:
                    raw = extras.get(f"{alias}_{option.key}")
                    if raw is not None:
                        break
        out[option.key] = coerce_option(option, raw)
    return out


def targets_json(doc: dict | None = None) -> dict:
    selected = selected_targets(doc) if doc is not None else []
    items = []
    for target in _unique_targets():
        avail, reason = (True, "")
        if target.available is not None:
            try:
                avail, reason = target.available()
            except Exception as err:            # noqa: BLE001 - optional tools
                avail, reason = False, str(err)
        items.append({
            "id": target.id,
            "label": target.label,
            "description": target.description,
            "outputs": list(target.outputs),
            "emulator": target.emulator,
            "machine": target.machine,
            "colors": target.colors,
            "engine": target.engine,
            "band_width": target.band_width,
            "artifact_suffix": target.artifact_suffix,
            "available": bool(avail),
            "unavailable_reason": reason,
            "selected": target.id in selected,
            "options": [{
                "key": option_key(target, option),
                "suffix": option.key,
                "label": option.label,
                "kind": option.kind,
                "default": option.default,
                "choices": list(option.choices),
                "help": option.help,
                "minimum": option.minimum,
                "maximum": option.maximum,
                "game_key": option.game_key,
                "on_value": option.on_value,
                "off_value": option.off_value,
            } for option in target.options],
        })
    return {"targets": items, "selected": selected}


def _display_rank(target: Target) -> int:
    try:
        return DISPLAY_ORDER.index(target.id)
    except ValueError:
        return len(DISPLAY_ORDER)


def _unique_targets() -> list[Target]:
    seen = set()
    out = []
    for target in all_targets().values():
        if target.id in seen:
            continue
        seen.add(target.id)
        out.append(target)
    return sorted(out, key=_display_rank)


def selection_issues(doc: dict) -> list[dict]:
    issues = []
    game = (doc or {}).get("game") or {}
    raw = game.get("targets") or []
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    for name in raw:
        if get_target(name) is None:
            issues.append({
                "level": "error", "section": "game", "id": "targets",
                "msg": f"unknown build target {name!r}",
            })
    if not raw:
        return issues
    for target_id in selected_targets(doc):
        target = get_target(target_id)
        if target is None:
            continue
        allowed = {option_key(target, o) for o in target.options}
        for key in (game.get("extras") or {}):
            if key.startswith(target.option_prefix) and key not in allowed:
                issues.append({
                    "level": "warn", "section": "game", "id": "targets",
                    "msg": f"{target.label}: unknown option {key!r}",
                })
        if target.validate is not None:
            ctx = BuildContext(slug="", gdir="", doc=doc,
                               options=target_options(doc, target),
                               env={}, py="", root="")
            try:
                issues.extend(target.validate(ctx))
            except Exception as err:        # noqa: BLE001 - report, don't crash
                issues.append({
                    "level": "error", "section": "game", "id": "targets",
                    "target": target.id,
                    "msg": f"{target.label} validation failed: {err}",
                })
    return issues


def validate_targets(ctx: BuildContext) -> list[dict]:
    issues = []
    for target_id in selected_targets(ctx.doc):
        target = get_target(target_id)
        if target is None:
            issues.append({
                "level": "error", "section": "game", "id": "targets",
                "msg": f"unknown build target {target_id!r}",
            })
            continue
        if target.available is not None:
            avail, reason = target.available()
            if not avail:
                issues.append({
                    "level": "error", "section": "game", "id": "targets",
                    "target": target.id,
                    "msg": f"{target.label}: {reason}",
                })
                continue
        if target.validate is not None:
            try:
                issues.extend(target.validate(ctx))
            except Exception as err:            # noqa: BLE001 - report, don't crash
                issues.append({
                    "level": "error", "section": "game", "id": "targets",
                    "target": target.id,
                    "msg": f"{target.label} validation failed: {err}",
                })
    return issues

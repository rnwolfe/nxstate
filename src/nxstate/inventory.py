"""Nornir-flavored single-file inventory: defaults ← groups ← host (host wins).
No secrets live here — only host/username/port/transport/group membership. Passwords resolve
per host from env/keyring at connection time."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import AppError, ExitCode

# Settings a host may inherit/override.
INHERIT_KEYS = ("host", "username", "transport", "port", "insecure", "timeout")


@dataclass
class Target:
    name: str
    settings: dict


def default_inventory_path() -> Path:
    if p := os.environ.get("NXSTATE_INVENTORY"):
        return Path(p)
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "nxstate" / "inventory.yaml"


def load_inventory(path: str | None) -> dict:
    p = Path(path) if path else default_inventory_path()
    if not p.exists():
        raise AppError(
            ExitCode.CONFIG,
            "NO_INVENTORY",
            f"inventory not found: {p}",
            "create it (defaults/groups/hosts YAML) or pass --inventory PATH",
        )
    import yaml

    return yaml.safe_load(p.read_text()) or {}


def _effective(inv: dict, name: str, hostdef: dict) -> dict:
    eff: dict = dict(inv.get("defaults") or {})
    for g in hostdef.get("groups") or []:
        eff.update((inv.get("groups") or {}).get(g) or {})
    eff.update({k: v for k, v in hostdef.items() if k != "groups"})
    eff.setdefault("host", name)  # a host with no explicit `host:` uses its inventory name
    return eff


def resolve(inv: dict, devices: tuple, groups: tuple, all_: bool) -> list[Target]:
    """Resolve --device (globs), --group, --all into a de-duplicated, sorted target list."""
    hosts: dict = inv.get("hosts") or {}
    chosen: dict[str, dict] = {}
    if all_:
        chosen.update(hosts)
    for g in groups or ():
        members = {n: hd for n, hd in hosts.items() if g in (hd.get("groups") or [])}
        if not members:
            raise AppError(
                ExitCode.NOT_FOUND,
                "GROUP_NOT_FOUND",
                f"no hosts in group {g!r}",
                "check group names in the inventory",
            )
        chosen.update(members)
    for pat in devices or ():
        matched = {n: hd for n, hd in hosts.items() if fnmatch.fnmatch(n, pat)}
        if not matched:
            raise AppError(
                ExitCode.NOT_FOUND,
                "DEVICE_NOT_FOUND",
                f"no inventory host matches {pat!r}",
                "check device names / globs",
            )
        chosen.update(matched)
    return [Target(name=n, settings=_effective(inv, n, chosen[n])) for n in sorted(chosen)]

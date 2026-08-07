"""Persistent blacklist of package IDs that are never offered for update.

File format: one package ID per line, ``#`` comments allowed, user-editable.
IDs never contain whitespace (verified in the winget table).
"""

from __future__ import annotations

import os
from pathlib import Path


def blacklist_path() -> Path:
    """Path to the blacklist file: ``%LOCALAPPDATA%\\winget-tui\\blacklist.txt``."""
    localappdata = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(localappdata) / "winget-tui" / "blacklist.txt"


def load_blacklist() -> set[str]:
    """Load the blacklist; tolerates any file content (never raises)."""
    path = blacklist_path()
    if not path.is_file():
        return set()
    ids: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        ids.add(stripped)
    return ids


def add(package_id: str) -> bool:
    """Add ``package_id`` to the blacklist; True if newly added."""
    ids = load_blacklist()
    if package_id in ids:
        return False
    path = blacklist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{package_id}\n")
    return True


def remove(package_id: str) -> bool:
    """Remove ``package_id`` from the blacklist; True if it was present."""
    ids = load_blacklist()
    if package_id not in ids:
        return False
    path = blacklist_path()
    remaining = [line for line in ids if line != package_id]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in sorted(remaining)), encoding="utf-8")
    return True

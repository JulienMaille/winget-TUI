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


def _read_lines(path: Path) -> list[str]:
    """Return the file's lines, tolerating missing/unreadable files."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()


def load_blacklist() -> set[str]:
    """Load the blacklist; tolerates any file content (never raises)."""
    path = blacklist_path()
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in _read_lines(path):
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
    # The file is user-editable and may lack a trailing newline; append one
    # first so the new entry doesn't glue onto the last line.
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if text and not text.endswith("\n"):
            with path.open("a", encoding="utf-8") as f:
                f.write("\n")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{package_id}\n")
    return True


def remove(package_id: str) -> bool:
    """Remove ``package_id`` from the blacklist; True if it was present."""
    ids = load_blacklist()
    if package_id not in ids:
        return False
    path = blacklist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Rewrite line-by-line: keep comments, blank lines, and ordering, and drop
    # only the removed ID's line(s) — ``load_blacklist`` strips comments, so a
    # naive set-rewrite would silently destroy the user's annotations.
    kept = [line for line in _read_lines(path) if line.strip() != package_id]
    path.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
    return True

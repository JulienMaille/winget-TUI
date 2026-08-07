"""Winget interaction: listing upgradable packages and running upgrades.

The winget build this targets (v1.29.x, French locale) has no ``--output``/JSON
flag on ``list``/``upgrade`` and no ``--exclude`` flag, so we parse the human
table for listing and pass explicit package IDs to ``winget upgrade``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

DASHES = re.compile(r"^\-+$")

_WINGET = "winget"


def _winget_path() -> str:
    """Absolute path to winget, or 'winget' to fall back to PATH.

    winget on Windows is an App Execution Alias (a 0-byte reparse-point shim
    in ``%LOCALAPPDATA%\\Microsoft\\WindowsApps``); spawning the bare name via
    ``CreateProcess`` is intermittently flaky across processes. Resolving the
    target once with ``shutil.which`` yields a robust concrete executable.
    """
    global _WINGET
    if _WINGET == "winget":
        resolved = shutil.which("winget")
        if resolved:
            _WINGET = resolved
    return _WINGET


class WingetError(RuntimeError):
    """Raised when a winget invocation fails."""


@dataclass(frozen=True)
class Package:
    name: str
    id: str
    version: str
    available: str
    source: str


def _run_winget(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run winget, raising WingetError on nonzero exit."""
    proc = subprocess.run(
        [_winget_path(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise WingetError(proc.stderr.strip() or proc.stdout.strip())
    return proc


def list_upgradable() -> list[Package]:
    """Return all packages with an available upgrade.

    Runs ``winget upgrade`` with no query, which prints the table of
    available upgrades.
    """
    proc = _run_winget(
        ["upgrade", "--accept-source-agreements", "--disable-interactivity"]
    )
    return parse_upgrade_output(proc.stdout)


def _dash_run_bounds(separator: str) -> list[int]:
    """Column start positions from the dash runs of the separator row."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, ch in enumerate(separator):
        if ch == "-":
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(separator)))
    return [start for start, _ in runs]


def _header_word_bounds(header: str) -> list[int]:
    """Column start positions from whitespace-delimited words in the header.

    Locale-independent: relies only on token separation, never on the header
    text itself (Nom/Name, Disponible/Available, ...).
    """
    bounds: list[int] = []
    in_word = False
    for i, ch in enumerate(header):
        if ch != " " and not in_word:
            bounds.append(i)
            in_word = True
        elif ch == " ":
            in_word = False
    if bounds and bounds[0] != 0:
        bounds.insert(0, 0)
    return bounds


def parse_upgrade_output(stdout: str) -> list[Package]:
    """Parse the ``winget upgrade`` table.

    Locale-independent column parser. The header row (the line above the
    dash separator) delimits the columns: each whitespace-delimited header
    word marks a column start. This handles both a spaced separator (dash
    runs aligned with the header) and the observed French-locale separator
    that is one continuous dash run. If the header yields fewer than 5
    columns, fall back to dash-run boundaries in the separator.

    The trailing summary line (e.g. French "18 mises a niveau disponibles."
    or English "Found N packages...") has an empty ID slice, so it is dropped
    by the whitespace check on the ID field.
    """
    lines = stdout.splitlines()
    separator_index = -1
    for i, line in enumerate(lines):
        if DASHES.match(line.strip()):
            separator_index = i
            break
    if separator_index < 1:
        return []

    separator = lines[separator_index]
    header = lines[separator_index - 1]
    bounds = _header_word_bounds(header)
    if len(bounds) < 5:
        bounds = _dash_run_bounds(separator)
    if len(bounds) < 5:
        return []

    packages: list[Package] = []
    for line in lines[separator_index + 1 :]:
        if not line.strip():
            continue
        fields = [
            line[bounds[j] : bounds[j + 1] if j + 1 < len(bounds) else len(line)].strip()
            for j in range(len(bounds))
        ]
        package_id = fields[1]
        if not package_id or any(ch.isspace() for ch in package_id):
            continue
        packages.append(
            Package(
                name=fields[0],
                id=package_id,
                version=fields[2],
                available=fields[3],
                source=fields[4],
            )
        )
    return packages


def build_update_args(ids: list[str], force: bool = False) -> list[str]:
    """Build the argv for upgrading the given package IDs.

    IDs are passed as positional queries (``winget upgrade [[-q] <query>...]``
    is variadic and matches by ID). No ``--uninstall-previous`` or
    ``--include-unknown``: default behavior only, so failures surface instead
    of being suppressed. ``force`` adds ``--force``, winget's escape hatch for
    refusing to overwrite a modified Portable package.
    """
    args = [
        "upgrade",
        *ids,
        "--silent",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    if force:
        args.append("--force")
    return args


def stream_upgrade(
    ids: list[str], on_line: Callable[[str], None], force: bool = False
) -> int:
    """Run the upgrade, streaming output lines to ``on_line``.

    Returns winget's exit code (0 = all succeeded, nonzero = some failed;
    per-package failures are visible in the streamed log).
    """
    proc = subprocess.Popen(
        [_winget_path(), *build_update_args(ids, force=force)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        on_line(line.rstrip("\r\n"))
    return proc.wait()

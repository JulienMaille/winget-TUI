"""Command-line interface for winget-tui.

No subcommand launches the TUI; ``list`` prints upgradable packages; the
``blacklist`` subcommands manage the persistent blacklist.
"""

from __future__ import annotations

import argparse
import sys

from winget_tui import blacklist, winget


def _print_table(packages: list[winget.Package]) -> None:
    for p in packages:
        print(f"{p.name:<40} {p.id:<40} {p.version:<12} {p.available:<12} {p.source}")


def _cmd_list(args: argparse.Namespace) -> int:
    try:
        packages = winget.list_upgradable()
    except winget.WingetError as exc:
        print(f"winget error: {exc}", file=sys.stderr)
        return 1
    blocked = blacklist.load_blacklist()
    _print_table([p for p in packages if p.id not in blocked])
    return 0


def _cmd_blacklist(args: argparse.Namespace) -> int:
    if args.action == "add":
        added = blacklist.add(args.package_id)
        print("added" if added else "already present")
    elif args.action == "remove":
        removed = blacklist.remove(args.package_id)
        print("removed" if removed else "not found")
    elif args.action == "list":
        ids = sorted(blacklist.load_blacklist())
        for package_id in ids:
            print(package_id)
        if not ids:
            print("(empty)")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="winget-tui",
        description="TUI + CLI for updating winget packages with a persistent blacklist.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="list packages with an available upgrade (blacklist filtered)")

    bl = sub.add_parser("blacklist", help="manage the persistent blacklist")
    bl_sub = bl.add_subparsers(dest="action", required=True)
    add_p = bl_sub.add_parser("add", help="blacklist a package ID")
    add_p.add_argument("package_id")
    rm_p = bl_sub.add_parser("remove", help="un-blacklist a package ID")
    rm_p.add_argument("package_id")
    bl_sub.add_parser("list", help="show the current blacklist")

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "list":
        sys.exit(_cmd_list(args))
    if args.command == "blacklist":
        sys.exit(_cmd_blacklist(args))
    # No subcommand: launch the TUI.
    from winget_tui.tui import WingetTuiApp

    WingetTuiApp().run()


if __name__ == "__main__":
    main()

"""Textual TUI for winget-tui: selectable upgradable-package list with a
persistent blacklist and a streamed update pass."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, ProgressBar, RichLog, Static

from winget_tui import blacklist, winget

BLOCKED_STYLE = "dim strike"


class UpdateTable(DataTable):
    """DataTable whose Enter triggers the app update and whose rows toggle
    selection when clicked.

    DataTable's own ``enter`` binding is ``show=False`` (hidden from the
    footer), so we re-declare it here with a visible label — per-key, the
    subclass binding replaces the base one in the binding merge. The action
    redirect is needed because DataTable would otherwise bind Enter to
    ``select_cursor``.
    """

    BINDINGS = [
        Binding("enter", "select_cursor", "Update selected"),
    ]

    def action_select_cursor(self) -> None:
        self.app.action_update()

    async def _on_click(self, event: events.Click) -> None:
        """Move the cursor to the clicked row, then toggle its selection."""
        meta = event.style.meta
        on_data_row = (
            "row" in meta
            and "column" in meta
            and not (self.show_header and meta.get("row") == -1)
            and not (self.show_row_labels and meta.get("column") == -1)
            and not (self.cursor_type != "row" and meta.get("out_of_bounds", False))
        )
        await super()._on_click(event)
        if on_data_row:
            self.app.action_toggle_selection()


class WingetTuiApp(App):
    """Checkbox-list TUI over ``winget upgrade``."""

    TITLE = "winget-tui"

    CSS = """
    #main {
        height: 1fr;
    }
    #table {
        height: 1fr;
    }
    #empty {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    #update_log {
        height: 1fr;
        display: none;
    }
    #log {
        height: 8;
    }
    #update_status {
        height: auto;
        display: none;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    #update_status_text {
        text-style: bold;
    }
    #update_bar {
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_selection", "Toggle selection"),
        Binding("a", "select_all", "Select all"),
        Binding("n", "clear_selection", "Clear selection"),
        Binding("b", "toggle_blacklist", "Blacklist/unblacklist"),
        Binding("h", "toggle_blacklist_view", "Show/hide blacklisted"),
        Binding("r", "refresh", "Refresh"),
        Binding("f", "toggle_force", "Force update"),
        Binding("enter", "update", "Update selected"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.packages: list[winget.Package] = []
        self.selected: dict[str, bool] = {}
        self.show_blacklist = False
        self.updating = False
        self.force_update = False
        self._last_stream_line = ""

    # --- widgets resolved in on_mount (set before any worker touches them) ---
    table: DataTable
    log_view: RichLog
    update_log: RichLog
    empty: Static
    update_status: Vertical
    update_status_text: Static
    update_bar: ProgressBar
    footer: Footer

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="main"):
            yield UpdateTable(id="table")
            yield Static("No updates available", id="empty")
            yield RichLog(id="update_log", wrap=True, auto_scroll=True)
        yield RichLog(id="log", wrap=True, auto_scroll=True)
        yield Footer()
        with Vertical(id="update_status"):
            yield Static("", id="update_status_text")
            yield ProgressBar(total=None, show_percentage=False, show_eta=False, id="update_bar")

    def on_mount(self) -> None:
        self.table = self.query_one("#table", DataTable)
        self.log_view = self.query_one("#log", RichLog)
        self.update_log = self.query_one("#update_log", RichLog)
        self.empty = self.query_one("#empty", Static)
        self.update_status = self.query_one("#update_status", Vertical)
        self.update_status_text = self.query_one("#update_status_text", Static)
        self.update_bar = self.query_one("#update_bar", ProgressBar)
        self.footer = self.query_one(Footer)

        self.table.cursor_type = "row"
        self.table.add_columns("[x]", "Name", "ID", "Version", "Available", "Source")
        self.empty.display = False
        self.sub_title = "Loading…"
        self.table.focus()
        self._refresh()

    # --- background work ---------------------------------------------------
    def _refresh(self) -> None:
        """Re-run list_upgradable in a worker, keeping the last good table on error."""
        self.run_worker(self._load_packages, thread=True, exit_on_error=False)

    def _load_packages(self) -> None:
        try:
            packages = winget.list_upgradable()
        except winget.WingetError as exc:
            self.call_from_thread(self.log_view.write, f"winget error: {exc}")
            return
        self.call_from_thread(self._apply_packages, packages)

    def _apply_packages(self, packages: list[winget.Package]) -> None:
        self.packages = packages
        present = {p.id for p in packages}
        self.selected = {pid: True for pid in self.selected if pid in present}
        self._rebuild_table()
        self.log_view.write(f"Refreshed: {len(packages)} upgradable")

    def _run_update(self, ids: list[str]) -> None:
        def on_line(line: str) -> None:
            self._last_stream_line = line
            self.call_from_thread(self.update_log.write, line)

        try:
            code = winget.stream_upgrade(ids, on_line, force=self.force_update)
        except Exception as exc:  # e.g. winget not on PATH
            self.call_from_thread(self._fail_update, str(exc))
            return
        self.call_from_thread(self._finish_update, code)

    # --- view updates ------------------------------------------------------
    def _current_package_id(self) -> str | None:
        table = self.table
        if not table.row_count:
            return None
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        return cell_key.row_key.value

    def _visible_packages(self, blocked: set[str]) -> list[winget.Package]:
        if self.show_blacklist:
            return self.packages
        return [p for p in self.packages if p.id not in blocked]

    def _rebuild_table(self) -> None:
        table = self.table
        blocked = blacklist.load_blacklist()
        prev_cursor = self._current_package_id()
        table.clear()

        visible_count = 0
        for pkg in self.packages:
            is_blocked = pkg.id in blocked
            if is_blocked and not self.show_blacklist:
                continue
            visible_count += 1
            if is_blocked:
                marker = Text("BL", style=BLOCKED_STYLE)
                cells: list = [
                    marker,
                    *(
                        Text(c, style=BLOCKED_STYLE)
                        for c in (pkg.name, pkg.id, pkg.version, pkg.available, pkg.source)
                    ),
                ]
            else:
                marker = (
                    Text("[x]", style="bold green")
                    if self.selected.get(pkg.id)
                    else Text("[ ]")
                )
                cells = [marker, pkg.name, pkg.id, pkg.version, pkg.available, pkg.source]
            table.add_row(*cells, key=pkg.id)

        self.empty.display = visible_count == 0
        if visible_count and prev_cursor in table.rows:
            table.move_cursor(row=table.get_row_index(prev_cursor))
        self._update_header()

    def _update_header(self) -> None:
        blocked = blacklist.load_blacklist()
        force = " · force" if self.force_update else ""
        self.sub_title = (
            f"{len(self.packages)} upgradable"
            f" · {0 if self.show_blacklist else len(blocked & {p.id for p in self.packages})} blacklisted hidden"
            f" · {len(self.selected)} selected{force}"
        )

    # --- update mode --------------------------------------------------------
    def _start_update(self, ids: list[str]) -> None:
        self.updating = True
        self.table.display = False
        self.empty.display = False
        self.log_view.display = False
        self.footer.display = False
        self.update_status.display = True
        self.update_status_text.update(f"Updating {len(ids)} packages…")
        self.sub_title = f"Updating {len(ids)} packages…"
        self.update_log.display = True
        self.update_log.clear()
        self.update_log.write(f"winget upgrade {' '.join(ids)}")
        self.run_worker(lambda: self._run_update(ids), thread=True, exit_on_error=False)

    def _restore_view(self) -> None:
        self.updating = False
        self.update_log.display = False
        self.update_status.display = False
        self.update_status_text.update("")
        self.footer.display = True
        self.log_view.display = True
        self.table.display = True
        self._rebuild_table()
        self.table.focus()

    def _finish_update(self, code: int) -> None:
        if code and self._last_stream_line:
            tail = self._last_stream_line.strip()
            if tail:
                self.update_log.write(f"Update finished. Exit code: {code} — {tail}")
                self.log_view.write(f"Update finished. Exit code: {code} — {tail}")
                self._restore_view()
                self._refresh()
                return
        self.update_log.write(f"Update finished. Exit code: {code}")
        self._restore_view()
        self.log_view.write(f"Update finished. Exit code: {code}")
        self._refresh()

    def _fail_update(self, message: str) -> None:
        self.update_log.write(f"Update error: {message}")
        self._restore_view()
        self.log_view.write(f"Update error: {message}")

    # --- actions -------------------------------------------------------------
    def action_toggle_selection(self) -> None:
        if self.updating:
            return
        pid = self._current_package_id()
        if pid is None or pid in blacklist.load_blacklist():
            return  # toggling blacklist is 'b', not selection
        self.selected[pid] = not self.selected.get(pid)
        self._rebuild_table()

    def action_select_all(self) -> None:
        if self.updating:
            return
        blocked = blacklist.load_blacklist()
        for pid in list(self.selected):
            self.selected[pid] = False
        for pkg in self.packages:
            if pkg.id not in blocked:
                self.selected[pkg.id] = True
        self._rebuild_table()

    def action_clear_selection(self) -> None:
        if self.updating:
            return
        self.selected = {}
        self._rebuild_table()

    def action_toggle_blacklist(self) -> None:
        if self.updating:
            return
        pid = self._current_package_id()
        if pid is None:
            return
        blocked = blacklist.load_blacklist()
        if pid in blocked:
            blacklist.remove(pid)
            self.log_view.write(f"Unblacklisted {pid}")
        else:
            blacklist.add(pid)
            self.selected.pop(pid, None)
            self.log_view.write(f"Blacklisted {pid}")
        self._rebuild_table()

    def action_toggle_blacklist_view(self) -> None:
        if self.updating:
            return
        self.show_blacklist = not self.show_blacklist
        self.log_view.write("Showing blacklisted" if self.show_blacklist else "Hiding blacklisted")
        self._rebuild_table()

    def action_toggle_force(self) -> None:
        if self.updating:
            return
        self.force_update = not self.force_update
        self.log_view.write(
            "Force mode on — updates run with --force (overwrites modified files)"
            if self.force_update
            else "Force mode off"
        )
        self._update_header()

    def action_refresh(self) -> None:
        if self.updating:
            return
        self.log_view.write("Refreshing…")
        self._refresh()

    def action_update(self) -> None:
        if self.updating:
            return
        blocked = blacklist.load_blacklist()
        ids = [p.id for p in self.packages if self.selected.get(p.id) and p.id not in blocked]
        if not ids:
            self.log_view.write("No packages selected")
            return
        self.selected = {}
        self._start_update(ids)


def run() -> None:
    WingetTuiApp().run()
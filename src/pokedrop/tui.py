"""Live terminal dashboard (Textual).

An always-on, auto-updating view of the watchlist: ticking countdowns, live
statuses, and a feed of alerts as they happen. The monitor engine runs inside
the app on the configured poll interval, so while the TUI is open you don't
need the separate `watch` daemon (don't run both — you'd get duplicate alerts).

Same rules as everywhere else in PokeDrop: this alerts and preps; it never buys.
"""

from __future__ import annotations

import json
import random
import time
import webbrowser
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, RichLog, Static
from textual.worker import get_current_worker

from .config import Settings
from .engine import events_path, run_once
from .models import Watch
from .prep import PREP_ITEMS, load_done, mark
from .state import load_state

_STATUS_LABEL = {
    "available": "🟢 available",
    "out_of_stock": "🔴 out of stock",
    "blocked": "🚧 blocked",
    "unknown": "⚪ unknown",
    "error": "⚠️ error",
}


def _fmt_secs(secs: float) -> str:
    if secs <= 0:
        return "NOW"
    d, r = divmod(int(secs), 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    if d:
        return f"{d}d {h:02}:{m:02}:{s:02}"
    return f"{h:02}:{m:02}:{s:02}"


def _drop_at(watch: Watch) -> datetime | None:
    """Best-known drop moment: drop_time if set, else local midnight of release_date."""
    dt = watch.drop_datetime
    if dt is not None:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if watch.release_date:
        try:
            day = datetime.fromisoformat(watch.release_date[:10])
            return day.astimezone()  # naive midnight -> local tz
        except ValueError:
            return None
    return None


def _status_text(watch: Watch, state: dict) -> str:
    if not watch.enabled:
        return "⏸ disabled"
    if watch.source == "reminder":
        return "⏰ reminder-only"
    ws = state.get("watches", {}).get(watch.id, {})
    raw = ws.get("last_status", "unknown")
    return _STATUS_LABEL.get(raw, raw)


class PrepScreen(Screen):
    """Tickable prep checklist. Enter toggles an item; Escape goes back."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("  Prep checklist — Enter toggles an item, Escape returns.",
                     id="prep-help")
        yield DataTable(id="prep-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#prep-table", DataTable)
        table.add_columns(("Done", "done"), ("Retailer", "retailer"), ("Task", "task"))
        done = load_done()
        for item in PREP_ITEMS:
            check = "✅" if item.id in done else "⬜️"
            task = f"{item.text}" + (f"  ({item.tip})" if item.tip else "")
            table.add_row(check, item.retailer, task, key=item.id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        item_id = event.row_key.value
        if item_id is None:
            return
        now_done = item_id not in load_done()
        mark(item_id, now_done)
        table = self.query_one("#prep-table", DataTable)
        table.update_cell(item_id, "done", "✅" if now_done else "⬜️")


class PokeDropApp(App):
    """PokeDrop live dashboard."""

    TITLE = "PokeDrop"
    SUB_TITLE = "alert & prep — you buy manually"

    CSS = """
    #topline {
        height: 2;
        padding: 0 1;
        background: $surface;
        color: $text;
    }
    #watchlist { height: 1fr; }
    #events {
        height: 10;
        border-top: heavy $primary;
        padding: 0 1;
    }
    #prep-help { height: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("c", "check_now", "Check now"),
        Binding("o", "open_url", "Open product"),
        Binding("p", "prep", "Prep list"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: Settings, watches: list[Watch], *,
                 auto_check: bool = True):
        super().__init__()
        self.settings = settings
        self.watches = watches
        self.auto_check = auto_check
        self.checking = False
        # First pass shortly after launch, then every poll_interval ± jitter.
        self.next_check_at = time.monotonic() + 3
        self._row_order: list[Watch] = []
        self._events_offset = 0

    # ---------- layout ----------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="topline")
        yield DataTable(id="watchlist", cursor_type="row")
        yield RichLog(id="events", wrap=True, markup=False, max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#watchlist", DataTable)
        table.add_columns(
            ("Product", "product"), ("Retailer", "retailer"), ("MSRP", "msrp"),
            ("Drop in", "countdown"), ("Source", "source"), ("Status", "status"),
        )
        self._row_order = sorted(
            self.watches, key=lambda w: (not w.enabled, w.release_date or "9999", w.name)
        )
        state = load_state()
        for w in self._row_order:
            table.add_row(
                w.name[:52],
                w.retailer[:24],
                f"${w.msrp_usd:.2f}" if w.msrp_usd else "—",
                "…",
                w.source,
                _status_text(w, state),
                key=w.id,
            )
        self._load_event_history()
        self.set_interval(1.0, self._tick)

    # ---------- event feed ----------

    def _feed_write(self, line: str) -> None:
        self.query_one("#events", RichLog).write(line)

    def _load_event_history(self) -> None:
        """Show the last few persisted events, then remember the file offset."""
        path = events_path()
        if not path.exists():
            self._feed_write("No events yet — alerts and reminders will appear here.")
            return
        try:
            raw = path.read_bytes()
        except OSError:
            return
        # Only count complete lines; a partial trailing write is picked up later.
        complete = raw.rfind(b"\n") + 1
        self._events_offset = complete
        lines = [ln for ln in raw[:complete].split(b"\n") if ln]
        for line in lines[-8:]:
            self._append_event_line(line.decode("utf-8", errors="replace"), notify=False)

    def _tail_events(self) -> None:
        """Append any events written since we last looked (works across processes).

        Reads in binary and only consumes newline-terminated lines, so a write
        that's mid-flight in another process is re-read whole on the next pass.
        """
        path = events_path()
        if not path.exists():
            return
        try:
            size = path.stat().st_size
            if size < self._events_offset:  # file was truncated/rotated
                self._events_offset = 0
            if size == self._events_offset:
                return
            with path.open("rb") as fh:
                fh.seek(self._events_offset)
                chunk = fh.read()
        except OSError:
            return
        complete = chunk.rfind(b"\n") + 1
        if complete == 0:
            return  # only a partial line so far — wait for its newline
        self._events_offset += complete
        for line in chunk[:complete].split(b"\n"):
            if line:
                self._append_event_line(line.decode("utf-8", errors="replace"), notify=True)

    def _append_event_line(self, line: str, *, notify: bool) -> None:
        line = line.strip()
        if not line:
            return
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            return
        try:
            ts = datetime.fromisoformat(str(ev.get("ts", ""))).astimezone().strftime("%H:%M:%S")
        except ValueError:
            ts = "--:--:--"
        self._feed_write(f"[{ts}] {ev.get('title', '(event)')}")
        if notify:
            self.bell()

    # ---------- ticking ----------

    def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        table = self.query_one("#watchlist", DataTable)
        soonest: tuple[float, Watch] | None = None

        for w in self._row_order:
            drop = _drop_at(w)
            if drop is None:
                continue
            secs = (drop - now).total_seconds()
            # "NOW" only within a one-hour grace window; long-past drops show "past".
            cell = _fmt_secs(secs) if secs > -3600 else "past"
            table.update_cell(w.id, "countdown", cell, update_width=True)
            if w.enabled and secs > 0 and (soonest is None or secs < soonest[0]):
                soonest = (secs, w)

        # Topline: next drop + monitor state.
        if soonest:
            secs, w = soonest
            next_drop = f"Next drop: {w.name[:40]} in {_fmt_secs(secs)}"
        else:
            next_drop = "Next drop: —"
        if self.checking:
            mon = "checking now…"
        elif not self.auto_check:
            mon = "auto-check off"
        else:
            mon = f"next check in {_fmt_secs(max(0, self.next_check_at - time.monotonic()))}"
        channels = []
        if self.settings.discord.enabled:
            channels.append("discord")
        if self.settings.email.enabled:
            channels.append("email")
        if self.settings.macos.enabled:
            channels.append("macos")
        chan = "+".join(channels) if channels else "NONE — edit settings.yaml!"
        self.query_one("#topline", Static).update(
            f" {next_drop}\n Monitor: {mon} · Alerts: {chan}"
        )

        if self.auto_check and not self.checking and time.monotonic() >= self.next_check_at:
            self.action_check_now()

    # ---------- check passes ----------

    def action_check_now(self) -> None:
        if self.checking:
            return
        self.checking = True
        self.run_worker(self._do_check, thread=True, exclusive=True, group="check")

    def _do_check(self) -> None:
        """Runs in a worker thread — no UI calls except via _safe_ui."""
        worker = get_current_worker()
        try:
            run_once(self.settings, self.watches, verbose=False, send_alerts=True,
                     should_abort=lambda: worker.is_cancelled)
        except Exception as e:
            self._safe_ui(worker, self._feed_write, f"[!] check pass failed: {e}")
        finally:
            self._safe_ui(worker, self._after_check)

    def _safe_ui(self, worker, fn, *args) -> None:
        """call_from_thread that tolerates app shutdown mid-pass.

        Textual can't interrupt a running thread worker; if the user quits while a
        network pass is in flight, the worker is flagged cancelled and the app may
        already be torn down — calling into the UI then would raise RuntimeError.
        """
        if worker.is_cancelled:
            return
        try:
            self.call_from_thread(fn, *args)
        except RuntimeError:
            pass  # app exited while the pass was finishing

    def _after_check(self) -> None:
        self.checking = False
        mon = self.settings.monitor
        jitter = random.randint(-mon.jitter_seconds, mon.jitter_seconds)
        self.next_check_at = time.monotonic() + max(30, mon.poll_interval_seconds + jitter)
        # Refresh statuses from the state file the engine just wrote.
        state = load_state()
        table = self.query_one("#watchlist", DataTable)
        for w in self._row_order:
            table.update_cell(w.id, "status", _status_text(w, state), update_width=True)
        self._tail_events()

    # ---------- other actions ----------

    def action_open_url(self) -> None:
        table = self.query_one("#watchlist", DataTable)
        row = table.cursor_row
        if 0 <= row < len(self._row_order):
            webbrowser.open(self._row_order[row].url)

    def action_prep(self) -> None:
        self.push_screen(PrepScreen())


def run_tui(settings: Settings, watches: list[Watch]) -> None:
    PokeDropApp(settings, watches).run()

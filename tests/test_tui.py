"""Headless tests for the Textual TUI (no display / no network needed)."""

import asyncio

from textual.widgets import DataTable

from pokedrop.prep import load_done
from pokedrop.tui import PokeDropApp, PrepScreen


def test_tui_headless(settings, watches):
    async def scenario():
        app = PokeDropApp(settings, watches, auto_check=False)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#watchlist", DataTable)
            assert table.row_count == len(watches)

            # One tick fills in countdowns; the column must be wide enough to show
            # the full value (regression: auto-width columns need update_width=True).
            await asyncio.sleep(1.2)
            await pilot.pause()
            first = watches[0].id
            cell = table.get_cell(first, "countdown")
            assert cell != "…"
            col = next(c for c in table.columns.values() if str(c.label) == "Drop in")
            assert col.get_render_width(table) >= len(cell)

            # Prep screen: open, toggle persists, toggle back, close.
            await pilot.press("p")
            await pilot.pause()
            assert isinstance(app.screen, PrepScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert len(load_done()) == 1
            await pilot.press("enter")
            await pilot.pause()
            assert len(load_done()) == 0
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, PrepScreen)

    asyncio.run(scenario())


def test_tui_event_tail_waits_for_newline(settings, watches):
    from pokedrop.engine import events_path

    async def scenario():
        app = PokeDropApp(settings, watches, auto_check=False)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            before = app._events_offset
            # A partial (newline-less) write must NOT be consumed yet.
            with events_path().open("ab") as fh:
                fh.write(b'{"ts": "2026-07-05T12:00:00+00:00", "title": "partial')
            app._tail_events()
            assert app._events_offset == before
            # Once the line is completed, it gets ingested.
            with events_path().open("ab") as fh:
                fh.write(b' line"}\n')
            app._tail_events()
            assert app._events_offset > before

    asyncio.run(scenario())

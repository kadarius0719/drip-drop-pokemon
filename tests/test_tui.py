"""Headless tests for the Textual TUI (no display / no network needed)."""

import asyncio

from textual.widgets import DataTable, Static, TabbedContent

from pokedrop.models import Event, Watch
from pokedrop.prep import load_done
from pokedrop.tui import ALL_TAB_ID, PokeDropApp, PrepScreen, _pane_id


def _demo_watches():
    return [
        Watch(id="w-anniv-1", name="Anniv ETB", retailer="Target", url="http://t/1",
              source="reminder", event="anniv", release_date="2026-09-16",
              drop_time="2026-09-16T08:00:00-04:00"),
        Watch(id="w-anniv-2", name="Anniv UPC", retailer="Best Buy", url="http://t/2",
              source="reminder", event="anniv", release_date="2026-09-16"),
        Watch(id="w-next-1", name="Next Set Booster Box", retailer="B&N", url="http://t/3",
              source="reminder", event="next-set", release_date="2026-11-14",
              drop_time="2026-11-14T09:00:00-05:00"),
        Watch(id="w-loose", name="Ungrouped thing", retailer="LGS", url="http://t/4",
              source="reminder", release_date="2026-10-01"),
    ]


def _demo_events():
    return {
        "anniv": Event(key="anniv", title="30th Celebration", notes="Wave 2: Dec 4"),
        "next-set": Event(key="next-set", title="Next Set"),
        "empty-ev": Event(key="empty-ev", title="No Watches Yet"),
    }


def test_pane_id_sanitizes():
    assert _pane_id("30th-celebration") == "tab-30th-celebration"
    assert _pane_id("weird key!") == "tab-weird-key-"


def test_tui_headless(settings, watches):
    """Original single-event flow: the All tab shows everything; prep round-trips."""
    async def scenario():
        app = PokeDropApp(settings, watches, auto_check=False)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # No events dict -> exactly one tab (All).
            assert list(app._tab_watches) == [ALL_TAB_ID]
            table = app.query_one(f"#{ALL_TAB_ID} DataTable", DataTable)
            assert table.row_count == len(watches)

            # One tick fills in countdowns; the column must be wide enough to show
            # the full value (regression: auto-width columns need update_width=True).
            await asyncio.sleep(1.2)
            await pilot.pause()
            first = app._tab_watches[ALL_TAB_ID][0].id
            cell = table.get_cell(first, "countdown")
            assert cell != "…"
            col = next(c for c in table.columns.values() if str(c.label) == "Drop in")
            assert col.get_render_width(table) >= len(cell)

            # Tab cycling with a single tab must be a safe no-op.
            await pilot.press("right_square_bracket")

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


def test_tabs_created_per_event_plus_all_and_other(settings):
    async def scenario():
        app = PokeDropApp(settings, _demo_watches(), _demo_events(), auto_check=False)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            panes = list(app._tab_watches)
            # All first; empty-ev has no watches so no tab; ungrouped -> Other.
            assert panes == [ALL_TAB_ID, _pane_id("anniv"), _pane_id("next-set"), "tab-other"]
            assert len(app._tab_watches[ALL_TAB_ID]) == 4
            assert len(app._tab_watches[_pane_id("anniv")]) == 2
            assert len(app._tab_watches["tab-other"]) == 1
            for pane_id, group in app._tab_watches.items():
                table = app.query_one(f"#{pane_id} DataTable", DataTable)
                assert table.row_count == len(group)

    asyncio.run(scenario())


def test_tab_switching_and_scoped_topline(settings):
    async def scenario():
        app = PokeDropApp(settings, _demo_watches(), _demo_events(), auto_check=False)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            tabs = app.query_one(TabbedContent)
            assert tabs.active == ALL_TAB_ID

            # ] cycles forward, [ back (with wrap-around).
            await pilot.press("right_square_bracket")
            assert tabs.active == _pane_id("anniv")
            await pilot.press("left_square_bracket")
            assert tabs.active == ALL_TAB_ID
            await pilot.press("left_square_bracket")
            assert tabs.active == "tab-other"

            # Topline "next drop" scopes to the active tab: on the next-set tab the
            # soonest drop is the November watch, not September's.
            tabs.active = _pane_id("next-set")
            await asyncio.sleep(1.2)
            await pilot.pause()
            top = str(app.query_one("#topline", Static).render())
            assert "Next Set Booster Box" in top

    asyncio.run(scenario())


def test_countdowns_update_in_background_tabs(settings):
    async def scenario():
        app = PokeDropApp(settings, _demo_watches(), _demo_events(), auto_check=False)
        async with app.run_test(size=(120, 36)) as pilot:
            await asyncio.sleep(1.2)
            await pilot.pause()
            # anniv tab is NOT active, yet its countdown cells must still tick.
            table = app.query_one(f"#{_pane_id('anniv')} DataTable", DataTable)
            assert table.get_cell("w-anniv-1", "countdown") != "…"

    asyncio.run(scenario())


def test_open_url_uses_active_tab(settings, monkeypatch):
    async def scenario():
        opened = []
        import pokedrop.tui as tui_mod
        monkeypatch.setattr(tui_mod.webbrowser, "open", opened.append)
        app = PokeDropApp(settings, _demo_watches(), _demo_events(), auto_check=False)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = "tab-other"
            await pilot.pause()
            app.action_open_url()
            assert opened == ["http://t/4"]  # the Other tab's only row

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

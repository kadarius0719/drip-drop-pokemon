#!/usr/bin/env python3
"""Regenerate the user-guide screenshots in docs/images/.

Run from the project root:  ./.venv/bin/python scripts/make_screenshots.py

Captures REAL output (no mockups):
  * tui-main.svg  — the live TUI dashboard (Textual's built-in SVG export)
  * tui-prep.svg  — the prep-checklist screen
  * cli-status.svg — the `run.py status` table (Rich SVG recording)

The shots use staged demo data (a temp POKEDROP_DATA_DIR with sample statuses,
events, and prep progress; the disabled live-check template watches are enabled
in-memory) so every feature is visible. Your real data/ is never touched.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

IMAGES = ROOT / "docs" / "images"
SIZE = (140, 36)


def stage_demo_data(data_dir: Path) -> None:
    """Seed state/events/prep so the screenshots show every feature in action."""
    data_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    def iso(mins_ago: int) -> str:
        return (now - timedelta(minutes=mins_ago)).isoformat()

    (data_dir / "state.json").write_text(json.dumps({
        "watches": {
            "etb-30th-target": {"last_status": "available", "last_checked": iso(1),
                                "block_until": None, "fired_reminders": []},
            "etb-30th-bestbuy": {"last_status": "out_of_stock", "last_checked": iso(1),
                                 "block_until": None, "fired_reminders": []},
            "etb-30th-bn": {"last_status": "blocked", "last_checked": iso(12),
                            "block_until": (now + timedelta(minutes=48)).isoformat(),
                            "fired_reminders": []},
        }
    }, indent=2))

    events = [
        {"ts": iso(47), "kind": "reminder",
         "title": "⏰ Drop soon: 30th Celebration Elite Trainer Box (Pokémon Center + retailers)",
         "message": "", "url": "", "watch_id": "etb-30th"},
        {"ts": iso(21), "kind": "reddit",
         "title": "📣 r/PokemonTCGDeals: [Target] 30th Celebration ETB preorder LIVE — MSRP $49.99",
         "message": "", "url": "", "watch_id": "reddit:PokemonTCGDeals"},
        {"ts": iso(1), "kind": "availability",
         "title": "🟢 IN STOCK: 30th Celebration ETB — Target (live check) (Target)",
         "message": "", "url": "", "watch_id": "etb-30th-target"},
    ]
    (data_dir / "events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))

    (data_dir / "prep.json").write_text(json.dumps(
        ["lgs-preorder", "pc-account", "pc-newsletter", "tool-discord"]))


def demo_config():
    from pokedrop.config import load_events, load_settings, load_watches
    from pokedrop.models import Event, Watch
    settings = load_settings(ROOT / "config" / "settings.example.yaml")
    settings.discord.enabled = True  # so the topline shows configured channels
    watches = load_watches(ROOT / "config" / "watchlist.example.yaml")
    for w in watches:
        w.enabled = True  # show the live-check template rows too
    events = load_events(ROOT / "config" / "watchlist.example.yaml")
    # A second (clearly-example) event so the tab bar is visible in the docs.
    events["next-set"] = Event(key="next-set", title="Next Set (example)",
                               notes="Example of a second drop event tab")
    watches += [
        Watch(id="demo-next-etb", name="Next Set Elite Trainer Box", retailer="Target",
              url="https://www.target.com/", source="reminder", event="next-set",
              msrp_usd=49.99, release_date="2026-11-14",
              drop_time="2026-11-14T09:00:00-05:00"),
        Watch(id="demo-next-bb", name="Next Set Booster Bundle", retailer="Best Buy",
              url="https://www.bestbuy.com/", source="reminder", event="next-set",
              msrp_usd=26.94, release_date="2026-11-14"),
    ]
    return settings, watches, events


async def shoot_tui() -> None:
    from textual.widgets import DataTable
    from pokedrop.tui import PokeDropApp

    settings, watches, events = demo_config()
    app = PokeDropApp(settings, watches, events, auto_check=False)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        # Make the topline read like a normal running monitor, not the test rig.
        app.auto_check = True
        app.next_check_at = time.monotonic() + 154
        await asyncio.sleep(1.3)  # let ticks fill countdowns + topline
        await pilot.pause()
        (IMAGES / "tui-main.svg").write_text(
            app.export_screenshot(title="PokeDrop — live dashboard (run.py ui)"))

        await pilot.press("p")
        await pilot.pause()
        await pilot.press("down", "down", "down", "down")  # show cursor mid-list
        await pilot.pause()
        (IMAGES / "tui-prep.svg").write_text(
            app.export_screenshot(title="PokeDrop — prep checklist (p)"))


def shoot_cli_status() -> None:
    from rich.console import Console
    from pokedrop.dashboard import render_cli

    _, watches, _events = demo_config()
    console = Console(record=True, width=150, file=open(os.devnull, "w"))
    render_cli(watches, console=console)
    (IMAGES / "cli-status.svg").write_text(
        console.export_svg(title="pokedrop status"))


def main() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        demo_data = Path(td) / "data"
        stage_demo_data(demo_data)
        os.environ["POKEDROP_DATA_DIR"] = str(demo_data)
        asyncio.run(shoot_tui())
        shoot_cli_status()
    for name in ("tui-main.svg", "tui-prep.svg", "cli-status.svg"):
        p = IMAGES / name
        print(f"  ✓ {p.relative_to(ROOT)}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

"""Render status: a rich CLI table and a standalone HTML dashboard."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

from .config import Settings, data_dir
from .models import Status, Watch
from .prep import PREP_ITEMS, load_done
from .state import load_state

_STATUS_LABEL = {
    "available": "🟢 available",
    "out_of_stock": "🔴 out of stock",
    "blocked": "🚧 blocked (reminders)",
    "reminder": "⏰ reminder-only",
    "unknown": "⚪ unknown",
    "error": "⚠️ error",
}


def _parse_release(watch: Watch) -> date | None:
    if not watch.release_date:
        return None
    try:
        return date.fromisoformat(watch.release_date[:10])
    except ValueError:
        return None


def _countdown(target: date | None) -> str:
    if target is None:
        return "—"
    days = (target - datetime.now(timezone.utc).date()).days
    if days > 1:
        return f"in {days} days"
    if days == 1:
        return "tomorrow"
    if days == 0:
        return "TODAY"
    return f"{-days} days ago"


def _status_for(watch: Watch, state: dict) -> str:
    if watch.source == "reminder":
        return "reminder"
    ws = state.get("watches", {}).get(watch.id, {})
    return ws.get("last_status", "unknown")


def render_cli(watches: list[Watch], console=None) -> None:
    from rich.console import Console
    from rich.table import Table

    state = load_state()
    console = console or Console()
    # Group by drop event when more than one is in play; otherwise keep it flat.
    grouped = sorted({w.event for w in watches})
    show_event = len(grouped) > 1
    table = Table(title="PokeDrop watchlist", header_style="bold")
    cols = (("Event",) if show_event else ()) + (
        "Product", "Retailer", "MSRP", "Release", "Countdown", "Source", "Status")
    for col in cols:
        table.add_column(col)

    for w in sorted(watches, key=lambda x: (x.event, x.release_date or "9999", x.name)):
        rel = _parse_release(w)
        row = (
            w.name,
            w.retailer,
            f"${w.msrp_usd:.2f}" if w.msrp_usd else "—",
            w.release_date or "TBA",
            _countdown(rel),
            w.source,
            _STATUS_LABEL.get(_status_for(w, state), _status_for(w, state)),
        )
        table.add_row(*(((w.event or "—",) if show_event else ()) + row))
    console.print(table)

    done = load_done()
    console.print(f"\nPrep: [bold]{len(done)}/{len(PREP_ITEMS)}[/bold] items complete "
                  f"(run `python run.py prep` for the checklist).")


def render_html(watches: list[Watch], settings: Settings, out_path: Path | None = None) -> Path:
    state = load_state()
    out_path = out_path or (data_dir() / "dashboard.html")
    done = load_done()

    rows = []
    show_event = len({w.event for w in watches}) > 1
    last_event = object()
    for w in sorted(watches, key=lambda x: (x.event, x.release_date or "9999", x.name)):
        if show_event and w.event != last_event:
            last_event = w.event
            label = escape(w.event or "Other")
            rows.append(f"""
      <tr><td colspan="7" style="background:#1a1a2e;font-weight:bold;">{label}</td></tr>""")
        rel = _parse_release(w)
        status = _status_for(w, state)
        rows.append(f"""
      <tr>
        <td><a href="{escape(w.url)}" target="_blank">{escape(w.name)}</a></td>
        <td>{escape(w.retailer)}</td>
        <td>{f"${w.msrp_usd:.2f}" if w.msrp_usd else "&mdash;"}</td>
        <td>{escape(w.release_date or "TBA")}</td>
        <td>{escape(_countdown(rel))}</td>
        <td class="src">{escape(w.source)}</td>
        <td>{escape(_STATUS_LABEL.get(status, status))}</td>
      </tr>""")

    prep_rows = []
    for item in PREP_ITEMS:
        check = "✅" if item.id in done else "⬜️"
        prep_rows.append(f"""
      <tr>
        <td>{check}</td><td>{escape(item.retailer)}</td>
        <td>{escape(item.text)}<div class="tip">{escape(item.tip)}</div></td>
      </tr>""")

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>PokeDrop Dashboard</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 24px; color: #222; }}
  h1 {{ margin-bottom: 2px; }} .sub {{ color: #888; margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
  th {{ background: #FFCB05; }}
  .src {{ color: #666; font-variant: small-caps; }}
  .tip {{ color: #888; font-size: 12px; }}
  .banner {{ background:#fff8db; border:1px solid #FFCB05; padding:10px 14px; border-radius:8px; }}
</style></head>
<body>
  <h1>PokeDrop — Pokémon 30th Celebration</h1>
  <p class="sub">Generated {generated}. Alerts &amp; prep only — you buy manually.</p>
  <p class="banner"><b>Prep: {len(done)}/{len(PREP_ITEMS)} complete.</b>
     This tool never carts, checks out, or creates accounts, and never evades anti-bot measures.</p>
  <h2>Watchlist</h2>
  <table>
    <tr><th>Product</th><th>Retailer</th><th>MSRP</th><th>Release</th>
        <th>Countdown</th><th>Source</th><th>Status</th></tr>
    {''.join(rows)}
  </table>
  <h2>Prep checklist</h2>
  <table>
    <tr><th></th><th>Retailer</th><th>Task</th></tr>
    {''.join(prep_rows)}
  </table>
</body></html>"""
    out_path.write_text(html, encoding="utf-8")
    return out_path

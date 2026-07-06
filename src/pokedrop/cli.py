"""Command-line interface for PokeDrop."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, config_dir, load_settings, load_watches
from .models import AlertEvent


def _load_or_exit():
    try:
        settings = load_settings()
        watches = load_watches()
    except ConfigError as e:
        print(f"Config error:\n{e}\n", file=sys.stderr)
        sys.exit(2)
    return settings, watches


def cmd_init(_args) -> None:
    cdir = config_dir()
    cdir.mkdir(parents=True, exist_ok=True)
    made = []
    for name in ("settings.yaml", "watchlist.yaml"):
        target = cdir / name
        example = cdir / f"{name.replace('.yaml', '.example.yaml')}"
        if target.exists():
            print(f"  · {name} already exists — leaving it alone.")
            continue
        if example.exists():
            shutil.copy(example, target)
            made.append(name)
            print(f"  ✓ created {name} from example.")
        else:
            print(f"  ! missing template {example.name}; cannot create {name}.")
    if made:
        print("\nNext: edit config/settings.yaml (Discord webhook, email, Best Buy key),")
        print("then run `python run.py test-alerts` to verify, and `python run.py status`.")


def cmd_status(args) -> None:
    settings, watches = _load_or_exit()
    from .config import load_events
    from .dashboard import render_cli
    if getattr(args, "event", None) is not None:
        events = load_events()
        if args.event not in events:
            print(f"Unknown event '{args.event}'. Defined: {', '.join(sorted(events)) or '(none)'}")
            raise SystemExit(2)
        watches = [w for w in watches if w.event == args.event]
    render_cli(watches)


def cmd_list(_args) -> None:
    _settings, watches = _load_or_exit()
    for w in watches:
        state = "on " if w.enabled else "off"
        print(f"[{state}] {w.id:28} {w.source:8} {w.retailer:16} {w.name}")


def cmd_check(args) -> None:
    settings, watches = _load_or_exit()
    from .engine import run_once
    print("Running one check pass…")
    run_once(settings, watches, verbose=True, send_alerts=not args.no_alerts)
    print("Done.")


def cmd_watch(_args) -> None:
    settings, watches = _load_or_exit()
    from .engine import watch_loop
    watch_loop(settings, watches)


def cmd_ui(_args) -> None:
    settings, watches = _load_or_exit()
    from .config import load_events
    from .tui import run_tui
    run_tui(settings, watches, load_events())


def cmd_dashboard(_args) -> None:
    settings, watches = _load_or_exit()
    from .dashboard import render_html
    path = render_html(watches, settings)
    print(f"Dashboard written to: {path}")
    print(f"Open it with: open {path}")


def cmd_test_alerts(_args) -> None:
    settings, _watches = _load_or_exit()
    from .alerts import dispatch
    event = AlertEvent(
        kind="test",
        title="✅ PokeDrop test alert",
        message="If you can read this, your alert channel is wired up correctly.",
        url="https://www.pokemoncenter.com/",
    )
    results = dispatch(settings, event)
    for channel, (ok, detail) in results.items():
        print(f"  {'✓' if ok else '✗'} {channel}: {detail}")
    if not any(ok for ok, _ in results.values()):
        print("\nNo channel succeeded. Check enabled/webhook_url/email settings in settings.yaml.")


def cmd_prep(args) -> None:
    from .prep import PREP_ITEMS, load_done, mark
    if args.done:
        ok = mark(args.done, True)
        print(f"  {'✓ marked done' if ok else '! unknown id'}: {args.done}")
        return
    if args.undo:
        ok = mark(args.undo, False)
        print(f"  {'✓ marked not-done' if ok else '! unknown id'}: {args.undo}")
        return
    done = load_done()
    current_retailer = None
    for item in PREP_ITEMS:
        if item.retailer != current_retailer:
            current_retailer = item.retailer
            print(f"\n{current_retailer}")
        box = "✅" if item.id in done else "⬜️"
        print(f"  {box} {item.id:22} {item.text}")
        if item.tip:
            print(f"       ↳ {item.tip}")
    print(f"\n{len(done)}/{len(PREP_ITEMS)} done. "
          f"Mark with: python run.py prep --done <id>  (undo: --undo <id>)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pokedrop", description="Pokémon drop alert-and-prep tool.")
    p.add_argument("--version", action="version", version=f"PokeDrop {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create config files from the example templates").set_defaults(func=cmd_init)
    st = sub.add_parser("status", help="show the watchlist + current statuses")
    st.add_argument("--event", help="only show watches for this drop event key")
    st.set_defaults(func=cmd_status)
    sub.add_parser("list", help="list configured watches").set_defaults(func=cmd_list)

    c = sub.add_parser("check", help="run one check pass (fires alerts)")
    c.add_argument("--no-alerts", action="store_true",
                   help="true dry run: check and print only — no alerts, no state changes")
    c.set_defaults(func=cmd_check)

    sub.add_parser("watch", help="run continuously as a monitor daemon").set_defaults(func=cmd_watch)
    sub.add_parser("ui", help="live auto-updating terminal dashboard (runs the monitor too)").set_defaults(func=cmd_ui)
    sub.add_parser("dashboard", help="write the HTML dashboard").set_defaults(func=cmd_dashboard)
    sub.add_parser("test-alerts", help="send a test alert to all enabled channels").set_defaults(func=cmd_test_alerts)

    pr = sub.add_parser("prep", help="show/update the prep checklist")
    pr.add_argument("--done", metavar="ID", help="mark a prep item complete")
    pr.add_argument("--undo", metavar="ID", help="mark a prep item not complete")
    pr.set_defaults(func=cmd_prep)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

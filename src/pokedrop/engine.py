"""The run loop: check watches, detect transitions, fire alerts + reminders + feeds."""

from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone

import requests

from .alerts import dispatch
from .checkers import RobotsCache, check_watch
from .config import Settings, data_dir
from .feeds import poll_reddit
from .models import AlertEvent, CheckResult, Status, Watch
from .reminders import due_reminders
from .state import get_watch_state, load_state, now_iso, parse_iso, save_state


def _should_skip_for_block(ws: dict, now: datetime) -> bool:
    block_until = parse_iso(ws.get("block_until"))
    return block_until is not None and now < block_until


def events_path():
    return data_dir() / "events.jsonl"


def log_event(event: AlertEvent) -> None:
    """Append an event to the persistent feed (data/events.jsonl).

    The TUI tails this file; it also serves as an audit trail of every alert.
    """
    try:
        with events_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": now_iso(),
                "kind": event.kind,
                "title": event.title,
                "message": event.message,
                "url": event.url,
                "watch_id": event.watch_id,
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass  # the feed is best-effort; never let logging break a check pass


def run_once(
    settings: Settings,
    watches: list[Watch],
    *,
    verbose: bool = True,
    send_alerts: bool = True,
    should_abort=None,
) -> list[CheckResult]:
    """One full pass: live-check eligible watches, fire reminders, poll community feeds.

    With send_alerts=False this is a true dry run: no alerts, no event log, and no
    state saved — so a dry run can never consume a reminder window or swallow an
    availability transition that the real monitor should alert on later.

    should_abort: optional zero-arg callable checked between watches so a host app
    (the TUI) can cut a long network pass short when the user quits.
    """
    state = load_state()
    now = datetime.now(timezone.utc)
    robots = RobotsCache(settings.monitor.user_agent) if settings.monitor.respect_robots_txt else None
    session = requests.Session()
    results: list[CheckResult] = []
    aborted = False

    for w in watches:
        if should_abort is not None and should_abort():
            aborted = True
            break
        if not w.enabled:
            continue
        if w.source == "reminder":
            # No live check by design — covered by date reminders below.
            continue

        ws = get_watch_state(state, w.id)
        if _should_skip_for_block(ws, now):
            if verbose:
                print(f"  · {w.id}: backing off until {ws['block_until']} (skip live check)")
            continue

        result = check_watch(w, session, settings, robots)
        results.append(result)
        prev = ws.get("last_status", "unknown")

        if result.status == Status.BLOCKED:
            until = now + timedelta(minutes=settings.monitor.backoff_on_block_minutes)
            ws["block_until"] = until.isoformat()

        if result.status == Status.AVAILABLE and prev != Status.AVAILABLE.value:
            if verbose:
                print(f"  ★ {w.id}: NOW AVAILABLE" + (" — alerting" if send_alerts else " (dry run)"))
            if send_alerts:
                event = AlertEvent(
                    kind="availability",
                    title=f"🟢 IN STOCK: {w.name} ({w.retailer})",
                    message=(
                        f"{w.name} looks available at {w.retailer} right now.\n"
                        f"Detected: {result.detail}\n"
                        + (f"MSRP: ${w.msrp_usd:.2f}\n" if w.msrp_usd else "")
                        + "Buy it manually now — respect the per-customer limit."
                    ),
                    url=w.url,
                    watch_id=w.id,
                )
                log_event(event)
                _report(dispatch(settings, event), w.id, verbose)
        elif verbose:
            print(f"  · {w.id}: {result.status} ({result.detail})")

        ws["last_status"] = result.status.value
        ws["last_checked"] = now_iso()

    # Reminders and the Reddit feed both consume one-shot state (fired lead windows,
    # seen post ids), so they only run when alerts will actually be sent — otherwise
    # a dry run (`check --no-alerts`) would silently eat a reminder forever.
    if send_alerts and not aborted:
        # Date-based reminders (independent of scraping).
        for event in due_reminders(watches, state, settings.reminders.lead_times_minutes, now=now):
            if verbose:
                print(f"  ⏰ reminder: {event.title}")
            log_event(event)
            _report(dispatch(settings, event), event.watch_id, verbose)

        # Community feed (Reddit) — legitimate early-warning signal.
        for event in poll_reddit(settings.reddit, state, settings.monitor.user_agent,
                                 settings.monitor.request_timeout_seconds):
            if verbose:
                print(f"  📣 feed: {event.title}")
            log_event(event)
            _report(dispatch(settings, event), event.watch_id, verbose)

    # Dry runs make no persistent changes at all.
    if send_alerts:
        save_state(state)
    return results


def _report(results: dict, watch_id: str, verbose: bool) -> None:
    for channel, (ok, detail) in results.items():
        if ok:
            continue
        if verbose:
            print(f"    ! {channel} failed for {watch_id}: {detail}")
        # Surface delivery failures in the event feed so the TUI shows them.
        # "(none)" (no channels configured) is already shown on the TUI topline.
        if channel != "(none)":
            log_event(AlertEvent(
                kind="alert_error",
                title=f"⚠️ {channel} alert failed ({watch_id}): {detail[:120]}",
                message=detail,
                watch_id=watch_id,
            ))


def watch_loop(settings: Settings, watches: list[Watch]) -> None:
    """Daemon: run_once forever, sleeping poll_interval ± jitter between passes."""
    interval = settings.monitor.poll_interval_seconds
    jitter = settings.monitor.jitter_seconds
    print(f"PokeDrop monitor started — {len(watches)} watch(es), "
          f"~{interval}s interval (+/- {jitter}s jitter). Ctrl-C to stop.")
    try:
        while True:
            stamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{stamp}] checking…")
            try:
                run_once(settings, watches, verbose=True, send_alerts=True)
            except Exception as e:  # keep the daemon alive across transient errors
                print(f"  ! pass failed: {e}")
            sleep_for = max(30, interval + random.randint(-jitter, jitter))
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("\nStopped.")

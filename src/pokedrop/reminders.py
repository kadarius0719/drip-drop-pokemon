"""Date-based reminders.

This path never touches a retailer — it's pure local scheduling off each watch's
`drop_time`. It's the reliable backbone: even if a retailer blocks live checks,
you still get pinged ahead of an announced drop so you're ready to buy manually.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import AlertEvent, Watch
from .state import get_watch_state


def _fmt_remaining(minutes: float) -> str:
    m = int(round(minutes))
    if m <= 1:
        return "now"
    if m < 90:
        return f"~{m} minutes"
    hours = m / 60.0
    if hours < 36:
        return f"~{round(hours)} hours"
    return f"~{round(hours / 24)} days"


def due_reminders(
    watches: list[Watch],
    state: dict,
    lead_times_minutes: list[int],
    now: datetime | None = None,
) -> list[AlertEvent]:
    """Return reminder alerts that are due now and haven't fired yet.

    Each configured lead time fires at most once per watch. If several lead windows
    are crossed in the same pass (e.g. the monitor started late, already inside 1h),
    we send a SINGLE alert for the most urgent one and mark the rest consumed — so
    you don't get a burst of contradictory "~1 day"/"~1 hour" messages at once.
    The message text reflects the ACTUAL time remaining, not the lead bucket.
    """
    now = now or datetime.now(timezone.utc)
    events: list[AlertEvent] = []

    for w in watches:
        if not w.enabled:
            continue
        drop = w.drop_datetime
        if drop is None:
            continue
        if drop.tzinfo is None:
            drop = drop.replace(tzinfo=timezone.utc)

        ws = get_watch_state(state, w.id)
        fired = set(ws.get("fired_reminders", []))
        minutes_until = (drop - now).total_seconds() / 60.0

        # Lead windows we've entered (drop not yet passed) and haven't fired.
        entered_unfired = [
            lead for lead in lead_times_minutes
            if str(lead) not in fired and 0 <= minutes_until <= lead
        ]
        if not entered_unfired:
            continue

        msg = (
            f"{w.name} at {w.retailer} drops in {_fmt_remaining(minutes_until)}.\n"
            f"Drop time: {drop.astimezone().strftime('%a %b %d, %I:%M %p %Z')}\n"
        )
        if w.msrp_usd:
            msg += f"MSRP: ${w.msrp_usd:.2f}\n"
        msg += "Have the page open, be logged in, payment + address saved."
        events.append(AlertEvent(
            kind="reminder",
            title=f"⏰ Drop soon: {w.name} ({w.retailer})",
            message=msg,
            url=w.url,
            watch_id=w.id,
        ))
        # Consume every lead window we've already entered, not just the one we fired.
        fired.update(str(lead) for lead in entered_unfired)
        ws["fired_reminders"] = sorted(fired, key=int)

    return events

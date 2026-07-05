from datetime import datetime, timedelta, timezone

from pokedrop.models import Watch
from pokedrop.reminders import _fmt_remaining, due_reminders

NOW = datetime(2026, 9, 16, 6, 0, 0, tzinfo=timezone.utc)


def _watch(drop):
    return Watch(id="t", name="Test ETB", retailer="PC", url="http://x",
                 msrp_usd=49.99, source="reminder", drop_time=drop.isoformat())


def test_single_fire_no_burst_and_dedup():
    # Starting 30 min out should fire ONE alert (not both 24h and 1h), phrased
    # from the real time remaining, and consume the larger entered windows.
    w = _watch(NOW + timedelta(minutes=30))
    state = {"watches": {}}

    ev = due_reminders([w], state, [1440, 60, 10], now=NOW)
    assert len(ev) == 1
    assert "~30 minutes" in ev[0].message
    assert state["watches"]["t"]["fired_reminders"] == ["60", "1440"]

    # Same moment again -> nothing re-fires.
    assert due_reminders([w], state, [1440, 60, 10], now=NOW) == []

    # 5 min out -> the 10-min lead fires once.
    ev3 = due_reminders([w], state, [1440, 60, 10], now=NOW + timedelta(minutes=25))
    assert len(ev3) == 1 and "~5 minutes" in ev3[0].message
    assert state["watches"]["t"]["fired_reminders"] == ["10", "60", "1440"]

    # After the drop -> nothing.
    assert due_reminders([w], state, [1440, 60, 10], now=NOW + timedelta(minutes=40)) == []


def test_normal_running_fires_only_24h_window():
    # ~23.3h before: only the 1440 window is entered.
    w = _watch(NOW + timedelta(minutes=1400))
    state = {"watches": {}}
    ev = due_reminders([w], state, [1440, 60, 10], now=NOW)
    assert len(ev) == 1
    assert "hours" in ev[0].message
    assert state["watches"]["t"]["fired_reminders"] == ["1440"]


def test_no_drop_time_never_fires():
    w = Watch(id="t", name="x", retailer="PC", url="http://x", source="reminder")
    assert due_reminders([w], {"watches": {}}, [1440, 60, 10], now=NOW) == []


def test_disabled_watch_never_fires():
    w = _watch(NOW + timedelta(minutes=30))
    w.enabled = False
    assert due_reminders([w], {"watches": {}}, [1440, 60, 10], now=NOW) == []


def test_fmt_remaining():
    assert _fmt_remaining(0.4) == "now"
    assert _fmt_remaining(1) == "now"
    assert _fmt_remaining(45) == "~45 minutes"
    assert _fmt_remaining(89) == "~89 minutes"
    assert _fmt_remaining(120) == "~2 hours"
    assert _fmt_remaining(2880) == "~2 days"

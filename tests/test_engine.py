import json

from pokedrop.engine import events_path, log_event, run_once
from pokedrop.models import AlertEvent
from pokedrop.state import load_state


def test_dry_run_is_side_effect_free(settings, watches):
    """`check --no-alerts` must not save state or write events, so it can never
    consume a reminder window or swallow an availability transition."""
    # With the example config: live watches are disabled, the rest are reminder-only,
    # and the Reddit feed only runs when alerts are on -> a dry run makes no network
    # calls and no writes.
    run_once(settings, watches, verbose=False, send_alerts=False)
    from pokedrop.config import data_dir
    assert not (data_dir() / "state.json").exists()
    assert not events_path().exists()


def test_log_event_appends_jsonl():
    log_event(AlertEvent(kind="test", title="t1", message="m", url="http://x", watch_id="w"))
    log_event(AlertEvent(kind="test", title="t2", message="m", url="", watch_id="w"))
    lines = events_path().read_text().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["title"] == "t1" and rec["kind"] == "test" and "ts" in rec

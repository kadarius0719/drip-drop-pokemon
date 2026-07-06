from pathlib import Path

import pytest

from pokedrop.config import ConfigError, load_events, load_settings, load_watches

EXAMPLE_WATCHLIST = Path(__file__).resolve().parent.parent / "config" / "watchlist.example.yaml"


def test_load_example_settings(settings):
    assert settings.reddit.enabled is True
    assert settings.macos.enabled is True
    assert settings.monitor.poll_interval_seconds == 180
    assert settings.reminders.lead_times_minutes == [1440, 60, 10]
    # Target has a built-in default web key even when unset.
    assert settings.target.web_key


def test_load_example_watchlist(watches):
    assert len(watches) == 18
    valid = {"page", "target", "bestbuy", "reminder"}
    assert all(w.source in valid for w in watches)
    # The three live-check templates ship disabled until product pages exist.
    disabled = [w for w in watches if not w.enabled]
    assert {w.source for w in disabled} == {"target", "bestbuy", "page"}
    # Flagship product present with correct MSRP.
    upc = next(w for w in watches if w.id == "upc-day-night-30th")
    assert upc.msrp_usd == 179.99


def test_duplicate_id_rejected(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text(
        "watches:\n"
        "  - {id: a, name: A, retailer: R, url: 'http://x'}\n"
        "  - {id: a, name: B, retailer: R, url: 'http://y'}\n"
    )
    with pytest.raises(ConfigError, match="duplicate"):
        load_watches(p)


def test_invalid_source_rejected(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("watches:\n  - {id: a, name: A, retailer: R, url: 'http://x', source: cart}\n")
    with pytest.raises(ConfigError, match="invalid source"):
        load_watches(p)


def test_missing_required_field_rejected(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("watches:\n  - {id: a, name: A, retailer: R}\n")  # no url
    with pytest.raises(ConfigError, match="url"):
        load_watches(p)


def test_missing_file_gives_helpful_error(tmp_path):
    with pytest.raises(ConfigError, match="init"):
        load_settings(tmp_path / "nope.yaml")


def test_example_events_section(watches):
    events = load_events(EXAMPLE_WATCHLIST)
    assert list(events) == ["30th-celebration"]
    assert events["30th-celebration"].title == "30th Celebration"
    assert events["30th-celebration"].notes  # wave dates present
    # Every shipped watch is tagged into the event.
    assert all(w.event == "30th-celebration" for w in watches)


def test_undefined_event_key_rejected(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text(
        "events:\n  real-ev: {title: Real}\n"
        "watches:\n"
        "  - {id: a, name: A, retailer: R, url: 'http://x', event: tyop-ev}\n"
    )
    with pytest.raises(ConfigError, match="undefined event 'tyop-ev'"):
        load_watches(p)


def test_event_optional_and_events_section_optional(tmp_path):
    p = tmp_path / "wl.yaml"
    p.write_text("watches:\n  - {id: a, name: A, retailer: R, url: 'http://x'}\n")
    assert load_events(p) == {}
    ws = load_watches(p)
    assert ws[0].event == ""


def test_blank_event_value_means_ungrouped(tmp_path):
    # `event:` with no value parses as YAML null — must mean ungrouped, not "None".
    p = tmp_path / "wl.yaml"
    p.write_text(
        "watches:\n"
        "  - id: a\n    name: A\n    retailer: R\n    url: 'http://x'\n    event:\n"
    )
    assert load_watches(p)[0].event == ""


def test_colliding_event_keys_rejected(tmp_path):
    # 'wave 1' and 'wave-1' both sanitize to tab id 'tab-wave-1' -> would crash the TUI.
    p = tmp_path / "wl.yaml"
    p.write_text(
        "events:\n  wave 1: {title: A}\n  wave-1: {title: B}\nwatches: []\n"
    )
    with pytest.raises(ConfigError, match="too similar"):
        load_events(p)


def test_reserved_event_keys_rejected(tmp_path):
    for key in ("all", "other"):
        p = tmp_path / f"wl-{key}.yaml"
        p.write_text(f"events:\n  {key}: {{title: X}}\nwatches: []\n")
        with pytest.raises(ConfigError, match="reserved"):
            load_events(p)

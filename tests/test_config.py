import pytest

from pokedrop.config import ConfigError, load_settings, load_watches


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

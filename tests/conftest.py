"""Shared test fixtures.

All tests run WITHOUT network: they use the example config files and construct
watches in-memory. An autouse fixture points POKEDROP_DATA_DIR at a temp dir so
tests never touch the real data/ state.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from pokedrop.config import load_settings, load_watches  # noqa: E402

EXAMPLE_SETTINGS = ROOT / "config" / "settings.example.yaml"
EXAMPLE_WATCHLIST = ROOT / "config" / "watchlist.example.yaml"


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Redirect all state/prep/event writes to a temp dir for every test."""
    monkeypatch.setenv("POKEDROP_DATA_DIR", str(tmp_path / "data"))
    yield


@pytest.fixture
def settings():
    return load_settings(EXAMPLE_SETTINGS)


@pytest.fixture
def watches():
    return load_watches(EXAMPLE_WATCHLIST)

"""Load and validate configuration and the watchlist."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .models import ALL_TAB_ID, OTHER_TAB_ID, Event, Watch, pane_id

# Project root = two levels up from this file (src/pokedrop/config.py -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def config_dir() -> Path:
    override = os.environ.get("POKEDROP_CONFIG_DIR")
    return Path(override) if override else PROJECT_ROOT / "config"


def data_dir() -> Path:
    override = os.environ.get("POKEDROP_DATA_DIR")
    d = Path(override) if override else PROJECT_ROOT / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class MonitorSettings:
    poll_interval_seconds: int = 180
    jitter_seconds: int = 45
    request_timeout_seconds: int = 20
    user_agent: str = (
        "PokeDropMonitor/1.0 (personal restock alert; not for resale automation)"
    )
    respect_robots_txt: bool = True
    backoff_on_block_minutes: int = 60


@dataclass
class ReminderSettings:
    lead_times_minutes: list[int] = field(default_factory=lambda: [1440, 60, 10])


@dataclass
class DiscordSettings:
    enabled: bool = False
    webhook_url: str = ""
    mention: str = ""


@dataclass
class MacNotifySettings:
    enabled: bool = False   # native macOS Notification Center pop-ups (osascript)


@dataclass
class EmailSettings:
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    use_tls: bool = True
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addrs: list[str] = field(default_factory=list)


@dataclass
class BestBuySettings:
    api_key: str = ""   # free key from https://developer.bestbuy.com/


@dataclass
class TargetSettings:
    # Target's public RedSky web key. Keys rotate occasionally; if Target checks
    # start failing, grab the current 'key=' value from a target.com network request.
    web_key: str = "9f36aeafbe60771e321a7cc95a78140772ab3e96"


@dataclass
class RedditFeedSettings:
    enabled: bool = False
    subreddits: list[str] = field(default_factory=lambda: ["PokemonTCGDeals"])
    # A post must contain at least one of these (case-insensitive) to alert.
    match_keywords: list[str] = field(default_factory=lambda: ["30th", "celebration"])
    # Reddit rate-limits unauthenticated feeds to ~1 req/min; keep this generous.
    min_interval_seconds: int = 120
    # Optional free OAuth app (recommended — unauthenticated access is often blocked).
    # Create an "installed app" at https://www.reddit.com/prefs/apps ; client_secret
    # is blank for installed apps. Leave client_id empty to use the public JSON feed.
    client_id: str = ""
    client_secret: str = ""


@dataclass
class Settings:
    monitor: MonitorSettings = field(default_factory=MonitorSettings)
    reminders: ReminderSettings = field(default_factory=ReminderSettings)
    discord: DiscordSettings = field(default_factory=DiscordSettings)
    email: EmailSettings = field(default_factory=EmailSettings)
    macos: MacNotifySettings = field(default_factory=MacNotifySettings)
    bestbuy: BestBuySettings = field(default_factory=BestBuySettings)
    target: TargetSettings = field(default_factory=TargetSettings)
    reddit: RedditFeedSettings = field(default_factory=RedditFeedSettings)


class ConfigError(Exception):
    pass


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(
            f"Missing config file: {path}\n"
            f"Run `python run.py init` to create it from the example template."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level.")
    return data


def load_settings(path: Optional[Path] = None) -> Settings:
    path = path or (config_dir() / "settings.yaml")
    raw = _load_yaml(path)

    mon = raw.get("monitor", {}) or {}
    rem = raw.get("reminders", {}) or {}
    alerts = raw.get("alerts", {}) or {}
    disc = alerts.get("discord", {}) or {}
    mail = alerts.get("email", {}) or {}
    mac = alerts.get("macos", {}) or {}
    bby = raw.get("bestbuy", {}) or {}
    tgt = raw.get("target", {}) or {}
    rdt = raw.get("reddit_feed", {}) or {}

    return Settings(
        monitor=MonitorSettings(
            poll_interval_seconds=int(mon.get("poll_interval_seconds", 180)),
            jitter_seconds=int(mon.get("jitter_seconds", 45)),
            request_timeout_seconds=int(mon.get("request_timeout_seconds", 20)),
            user_agent=str(mon.get("user_agent", MonitorSettings.user_agent)),
            respect_robots_txt=bool(mon.get("respect_robots_txt", True)),
            backoff_on_block_minutes=int(mon.get("backoff_on_block_minutes", 60)),
        ),
        reminders=ReminderSettings(
            lead_times_minutes=list(rem.get("lead_times_minutes", [1440, 60, 10])),
        ),
        discord=DiscordSettings(
            enabled=bool(disc.get("enabled", False)),
            webhook_url=str(disc.get("webhook_url", "")).strip(),
            mention=str(disc.get("mention", "")).strip(),
        ),
        email=EmailSettings(
            enabled=bool(mail.get("enabled", False)),
            smtp_host=str(mail.get("smtp_host", "smtp.gmail.com")),
            smtp_port=int(mail.get("smtp_port", 587)),
            use_tls=bool(mail.get("use_tls", True)),
            username=str(mail.get("username", "")),
            password=str(mail.get("password", "")),
            from_addr=str(mail.get("from_addr", "")),
            to_addrs=list(mail.get("to_addrs", []) or []),
        ),
        macos=MacNotifySettings(
            enabled=bool(mac.get("enabled", False)),
        ),
        bestbuy=BestBuySettings(
            api_key=str(bby.get("api_key", "")).strip(),
        ),
        target=TargetSettings(
            web_key=str(tgt.get("web_key", TargetSettings.web_key)).strip()
            or TargetSettings.web_key,
        ),
        reddit=RedditFeedSettings(
            enabled=bool(rdt.get("enabled", False)),
            subreddits=list(rdt.get("subreddits", ["PokemonTCGDeals"]) or ["PokemonTCGDeals"]),
            match_keywords=list(rdt.get("match_keywords", ["30th", "celebration"]) or []),
            min_interval_seconds=int(rdt.get("min_interval_seconds", 120)),
            client_id=str(rdt.get("client_id", "")).strip(),
            client_secret=str(rdt.get("client_secret", "")).strip(),
        ),
    )


def _events_from_raw(raw: dict, path: Path) -> dict[str, Event]:
    section = raw.get("events", {}) or {}
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: 'events' must be a mapping of key -> {{title, notes}}.")
    events: dict[str, Event] = {}
    pane_ids: dict[str, str] = {}  # sanitized pane id -> event key that claimed it
    for key, val in section.items():
        key = str(key)
        val = val or {}
        if not isinstance(val, dict):
            raise ConfigError(f"{path}: event '{key}' must be a mapping (title/notes).")
        # Event keys become TUI tab widget ids after sanitization; collisions
        # (with each other or the reserved All/Other tabs) would crash the TUI
        # at startup with a widget-id traceback — reject here with a YAML-facing
        # error instead.
        pid = pane_id(key)
        if pid in (ALL_TAB_ID, OTHER_TAB_ID):
            raise ConfigError(
                f"{path}: event key '{key}' clashes with the reserved "
                f"'{pid.removeprefix('tab-')}' tab. Pick another key."
            )
        if pid in pane_ids:
            raise ConfigError(
                f"{path}: event keys '{pane_ids[pid]}' and '{key}' are too similar "
                f"(both become tab id '{pid}'). Rename one."
            )
        pane_ids[pid] = key
        events[key] = Event(
            key=key,
            title=str(val.get("title", key)),
            notes=str(val.get("notes", "")),
        )
    return events


def load_events(path: Optional[Path] = None) -> dict[str, Event]:
    """Parse the optional `events:` section of the watchlist (drop-event tabs)."""
    path = path or (config_dir() / "watchlist.yaml")
    return _events_from_raw(_load_yaml(path), path)


def load_watches(path: Optional[Path] = None) -> list[Watch]:
    path = path or (config_dir() / "watchlist.yaml")
    raw = _load_yaml(path)
    entries = raw.get("watches", []) or []
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: 'watches' must be a list.")
    # Same raw mapping — one read, so watches are always validated against the
    # events snapshot from the same parse.
    event_keys = set(_events_from_raw(raw, path))

    watches: list[Watch] = []
    seen_ids: set[str] = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise ConfigError(f"{path}: watch #{i} must be a mapping.")
        for required in ("id", "name", "retailer", "url"):
            if not e.get(required):
                raise ConfigError(f"{path}: watch #{i} is missing required field '{required}'.")
        wid = str(e["id"])
        if wid in seen_ids:
            raise ConfigError(f"{path}: duplicate watch id '{wid}'.")
        seen_ids.add(wid)
        source = str(e.get("source", "page")).lower()
        valid_sources = {"page", "target", "bestbuy", "reminder"}
        if source not in valid_sources:
            raise ConfigError(
                f"{path}: watch '{wid}' has invalid source '{source}'. "
                f"Valid: {', '.join(sorted(valid_sources))}."
            )
        # `or ""` so a blank `event:` line (YAML null) means ungrouped, not "None".
        event = str(e.get("event") or "")
        if event and event not in event_keys:
            # Reject typos loudly — a silently misfiled watch would hide in the wrong tab.
            raise ConfigError(
                f"{path}: watch '{wid}' references undefined event '{event}'. "
                f"Add it to the 'events:' section or fix the key. "
                f"Defined: {', '.join(sorted(event_keys)) or '(none)'}."
            )
        watches.append(
            Watch(
                id=wid,
                name=str(e["name"]),
                retailer=str(e["retailer"]),
                url=str(e["url"]),
                source=source,
                tcin=str(e.get("tcin", "")),
                sku=str(e.get("sku", "")),
                msrp_usd=(float(e["msrp_usd"]) if e.get("msrp_usd") not in (None, "") else None),
                release_date=(str(e["release_date"]) if e.get("release_date") else None),
                preorder_date=(str(e["preorder_date"]) if e.get("preorder_date") else None),
                drop_time=(str(e["drop_time"]) if e.get("drop_time") else None),
                in_stock_keywords=list(e.get("in_stock_keywords", []) or []),
                out_of_stock_keywords=list(e.get("out_of_stock_keywords", []) or []),
                enabled=bool(e.get("enabled", True)),
                notes=str(e.get("notes", "")),
                event=event,
            )
        )
    return watches

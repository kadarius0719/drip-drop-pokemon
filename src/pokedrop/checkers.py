"""Availability checking, one adapter per retailer "source".

Design constraints (these are the whole point — do not "fix" them):
  * We identify ourselves with a descriptive User-Agent and honor robots.txt.
  * We ONLY use sanctioned/public data paths:
      - Best Buy: the official free developer API.
      - Target: the intentionally-public RedSky fulfillment API.
      - "page": a polite keyword check, meant for LOW-bot-protection sites (e.g. B&N).
  * If a retailer signals a block/rate-limit (401/403/429/503), we mark the watch
    BLOCKED and back off. We do NOT rotate proxies, spoof fingerprints, solve
    CAPTCHAs, or defeat queues. Heavily protected retailers (Pokémon Center,
    Walmart, GameStop) should use source="reminder" instead of being scraped.
"""

from __future__ import annotations

import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from .models import CheckResult, Status, Watch

DEFAULT_IN_STOCK = [
    "add to cart", "add to bag", "add to basket",
    "pre-order", "preorder", "pre order", "buy now",
]
DEFAULT_OUT_OF_STOCK = [
    "sold out", "out of stock", "out-of-stock", "currently unavailable",
    "coming soon", "notify me", "email when available", "temporarily out of stock",
]

BLOCK_STATUSES = {401, 403, 429, 503}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RobotsCache:
    """Caches robots.txt per host so we only fetch it once."""

    def __init__(self, user_agent: str):
        self.user_agent = user_agent
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{root}/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None
            self._cache[root] = rp
        rp = self._cache[root]
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True


# --------------------------------------------------------------------------- #
# Source adapters
# --------------------------------------------------------------------------- #

def check_page(watch, session, user_agent, timeout, robots) -> CheckResult:
    """Polite keyword check of a normal product page. For LOW-bot-protection sites."""
    if robots is not None and not robots.allowed(watch.url):
        return CheckResult(watch.id, Status.BLOCKED,
                           "Disallowed by robots.txt — using date reminders instead.",
                           checked_at=_now())
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = session.get(watch.url, timeout=timeout, headers=headers)
    except requests.RequestException as e:
        return CheckResult(watch.id, Status.ERROR, f"Request failed: {e}", checked_at=_now())

    if resp.status_code in BLOCK_STATUSES:
        return CheckResult(watch.id, Status.BLOCKED,
                           f"HTTP {resp.status_code} (anti-bot/rate limit). Not evading.",
                           http_status=resp.status_code, checked_at=_now())
    if resp.status_code != 200:
        return CheckResult(watch.id, Status.ERROR, f"Unexpected HTTP {resp.status_code}",
                           http_status=resp.status_code, checked_at=_now())

    text = resp.text.lower()
    in_kw = [k.lower() for k in (watch.in_stock_keywords or DEFAULT_IN_STOCK)]
    out_kw = [k.lower() for k in (watch.out_of_stock_keywords or DEFAULT_OUT_OF_STOCK)]
    in_hit = next((k for k in in_kw if k in text), None)
    out_hit = next((k for k in out_kw if k in text), None)

    if in_hit and not out_hit:
        return CheckResult(watch.id, Status.AVAILABLE, f"matched '{in_hit}'", 200, _now())
    if out_hit and not in_hit:
        return CheckResult(watch.id, Status.OUT_OF_STOCK, f"matched '{out_hit}'", 200, _now())
    if in_hit and out_hit:
        return CheckResult(watch.id, Status.OUT_OF_STOCK,
                           f"ambiguous — '{in_hit}' and '{out_hit}' both present; refine keywords",
                           200, _now())
    return CheckResult(watch.id, Status.UNKNOWN, "no keywords matched", 200, _now())


def check_target(watch, session, user_agent, timeout, web_key) -> CheckResult:
    """Target RedSky public fulfillment API by TCIN.

    RedSky is intentionally public; still, Target IP-blocks aggressive callers, so
    the caller keeps intervals generous and we back off on any block signal.
    """
    if not watch.tcin:
        return CheckResult(watch.id, Status.ERROR, "source=target requires a 'tcin'", checked_at=_now())
    endpoint = "https://redsky.target.com/redsky_aggregations/v1/web/pdp_fulfillment_v1"
    params = {
        "key": web_key,
        "tcin": watch.tcin,
        "is_bot": "false",
        "pricing_store_id": "3991",
    }
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    try:
        resp = session.get(endpoint, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return CheckResult(watch.id, Status.ERROR, f"Request failed: {e}", checked_at=_now())

    if resp.status_code in BLOCK_STATUSES:
        return CheckResult(watch.id, Status.BLOCKED,
                           f"RedSky returned HTTP {resp.status_code}; backing off (not evading).",
                           http_status=resp.status_code, checked_at=_now())
    if resp.status_code != 200:
        return CheckResult(watch.id, Status.ERROR, f"RedSky HTTP {resp.status_code}",
                           http_status=resp.status_code, checked_at=_now())
    try:
        data = resp.json()
        fulfillment = data["data"]["product"]["fulfillment"]
        ship = fulfillment.get("shipping_options", {}) or {}
        status = str(ship.get("availability_status", "")).upper()
    except (ValueError, KeyError, TypeError) as e:
        return CheckResult(watch.id, Status.UNKNOWN, f"unexpected RedSky shape: {e}",
                           http_status=200, checked_at=_now())

    if status in ("IN_STOCK", "PRE_ORDER_SELLABLE", "LIMITED_STOCK"):
        return CheckResult(watch.id, Status.AVAILABLE, f"RedSky shipping={status}", 200, _now())
    if status:
        return CheckResult(watch.id, Status.OUT_OF_STOCK, f"RedSky shipping={status}", 200, _now())
    return CheckResult(watch.id, Status.UNKNOWN, "RedSky returned no shipping status", 200, _now())


def check_bestbuy(watch, session, user_agent, timeout, api_key) -> CheckResult:
    """Best Buy sanctioned developer API by SKU."""
    if not api_key:
        return CheckResult(watch.id, Status.ERROR,
                           "source=bestbuy needs bestbuy.api_key in settings.yaml", checked_at=_now())
    if not watch.sku:
        return CheckResult(watch.id, Status.ERROR, "source=bestbuy requires a 'sku'", checked_at=_now())
    endpoint = f"https://api.bestbuy.com/v1/products(sku={watch.sku})"
    params = {
        "apiKey": api_key,
        "format": "json",
        "show": "sku,name,onlineAvailability,orderable,regularPrice",
    }
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    try:
        resp = session.get(endpoint, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return CheckResult(watch.id, Status.ERROR, f"Request failed: {e}", checked_at=_now())

    if resp.status_code == 403:
        return CheckResult(watch.id, Status.ERROR,
                           "Best Buy API 403 — check your API key / rate limits.",
                           http_status=403, checked_at=_now())
    if resp.status_code != 200:
        return CheckResult(watch.id, Status.ERROR, f"Best Buy HTTP {resp.status_code}",
                           http_status=resp.status_code, checked_at=_now())
    try:
        products = resp.json().get("products", [])
        if not products:
            return CheckResult(watch.id, Status.UNKNOWN, "SKU not found in Best Buy catalog",
                               200, _now())
        p = products[0]
        orderable = str(p.get("orderable", "")).lower()
        online = p.get("onlineAvailability", False)
    except (ValueError, KeyError, TypeError) as e:
        return CheckResult(watch.id, Status.UNKNOWN, f"unexpected Best Buy shape: {e}", 200, _now())

    if online or orderable in ("available", "preorder", "backorder"):
        return CheckResult(watch.id, Status.AVAILABLE,
                           f"orderable={orderable}, online={online}", 200, _now())
    return CheckResult(watch.id, Status.OUT_OF_STOCK,
                       f"orderable={orderable}, online={online}", 200, _now())


def check_watch(watch: Watch, session: requests.Session, settings, robots) -> CheckResult:
    """Dispatch a watch to the right source adapter."""
    ua = settings.monitor.user_agent
    timeout = settings.monitor.request_timeout_seconds
    if watch.source == "reminder":
        return CheckResult(watch.id, Status.UNKNOWN,
                           "reminder-only (no live check by design)", checked_at=_now())
    if watch.source == "target":
        return check_target(watch, session, ua, timeout, settings.target.web_key)
    if watch.source == "bestbuy":
        return check_bestbuy(watch, session, ua, timeout, settings.bestbuy.api_key)
    return check_page(watch, session, ua, timeout, robots)

"""Core data types for watches, check results, and alert events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Optional


class Status(StrEnum):
    UNKNOWN = "unknown"            # page fetched but couldn't tell
    OUT_OF_STOCK = "out_of_stock"  # sold out / coming soon / notify-me
    AVAILABLE = "available"        # in stock / preorder live / add-to-cart present
    BLOCKED = "blocked"            # retailer blocked the automated check (we do NOT evade)
    ERROR = "error"               # network/other failure


# Statuses worth pinging the user about when a watch transitions INTO them.
ALERTABLE_TRANSITIONS = {Status.AVAILABLE}


@dataclass
class Watch:
    """A single product-at-a-retailer being tracked.

    `source` decides HOW availability is checked:
      * "bestbuy"  -> Best Buy's sanctioned developer API (needs `sku` + api key)
      * "target"   -> Target's public RedSky fulfillment API (needs `tcin`)
      * "page"     -> polite keyword check of a normal product page (low-bot retailers)
      * "reminder" -> no live check at all; date-based reminders only. Use this for
                      heavily bot-protected retailers (Pokémon Center, Walmart, GameStop)
                      where live polling would mean evading anti-bot measures.
    """

    id: str
    name: str
    retailer: str
    url: str
    source: str = "page"
    tcin: str = ""              # Target product id (for source=target)
    sku: str = ""               # Best Buy SKU (for source=bestbuy)
    msrp_usd: Optional[float] = None
    release_date: Optional[str] = None      # street date, human string e.g. "2026-09-16"
    preorder_date: Optional[str] = None     # when preorders open, human string
    drop_time: Optional[str] = None         # precise ISO8601 w/ tz for reminders, optional
    in_stock_keywords: list[str] = field(default_factory=list)
    out_of_stock_keywords: list[str] = field(default_factory=list)
    enabled: bool = True
    notes: str = ""

    @property
    def drop_datetime(self) -> Optional[datetime]:
        if not self.drop_time:
            return None
        try:
            return datetime.fromisoformat(self.drop_time)
        except ValueError:
            return None


@dataclass
class CheckResult:
    watch_id: str
    status: Status
    detail: str = ""
    http_status: Optional[int] = None
    checked_at: str = ""


@dataclass
class AlertEvent:
    """Something worth telling the user about."""

    kind: str          # "availability" | "reminder" | "test" | "block"
    title: str
    message: str
    url: str = ""
    watch_id: str = ""

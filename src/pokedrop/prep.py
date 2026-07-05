"""Prep checklist — the "be ready to buy manually" half of the tool.

These items encode where the MSRP shots actually are (per research) and the
account/payment prep that makes a manual checkout fast. YOU do each of these
yourself; the tool just tracks them. Nothing here automates a purchase.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import data_dir


@dataclass
class PrepItem:
    id: str
    retailer: str
    text: str
    tip: str = ""


# Ordered roughly best-MSRP-shot first.
PREP_ITEMS: list[PrepItem] = [
    # --- Setup for this tool ---
    PrepItem("tool-discord", "PokeDrop", "Create a Discord webhook and paste it into settings.yaml",
             "Server Settings → Integrations → Webhooks → New Webhook → Copy URL."),
    PrepItem("tool-email", "PokeDrop", "Set up an app password + email alerts in settings.yaml",
             "Gmail: enable 2FA, then create an App Password; use it as the SMTP password."),
    PrepItem("tool-bestbuy-key", "PokeDrop", "Get a free Best Buy developer API key",
             "https://developer.bestbuy.com/ — enables clean, sanctioned stock checks."),
    PrepItem("tool-reddit", "PokeDrop", "Enable the Reddit r/PokemonTCGDeals feed in settings.yaml",
             "Best legit early-warning that a preorder just went live somewhere."),

    # --- Local Game Store: the best MSRP path, zero bot competition ---
    PrepItem("lgs-preorder", "Local Game Store",
             "Call/email your local card shop to preorder 30th Celebration items",
             "LGS allocate by order history + organized play. This is the calmest MSRP shot."),

    # --- Pokémon Center: first-party, but hyped drops sit behind a randomized queue ---
    PrepItem("pc-account", "Pokémon Center", "Create a Pokémon Center account; save payment + address",
             "Preorders drop quietly ~78 days before release; be ready ahead of time."),
    PrepItem("pc-newsletter", "Pokémon Center", "Sign up for the Pokémon Center email newsletter",
             "Main sanctioned way to catch quiet drops without hammering the site."),
    PrepItem("pc-clean-checkout", "Pokémon Center", "Plan to disable VPN/ad-blocker for PC checkout",
             "Queue-it + DataDome/Imperva flag VPNs & datacenter IPs; they break checkout."),

    # --- Target: public app checks out fastest; RedCard helps ---
    PrepItem("target-account", "Target", "Create a Target account; save payment + address in the app",
             "The Target app checks out faster than target.com on hot drops."),
    PrepItem("target-redcard", "Target", "Consider a RedCard for 5% off + occasional early access", ""),

    # --- Walmart: first-party only, low quantities ---
    PrepItem("walmart-account", "Walmart", "Create a Walmart account; save payment + address",
             "Only buy 'Sold & shipped by Walmart'. Keep qty to 1–2 — more trips anti-bot cancels."),

    # --- Best Buy: sanctioned API + occasional exclusives ---
    PrepItem("bestbuy-account", "Best Buy", "Create a Best Buy account; save payment + address",
             "Restocks cluster Tue/Thu early mornings."),

    # --- Barnes & Noble: the low-competition 'hidden gem' ---
    PrepItem("bn-account", "Barnes & Noble", "Create a BN.com account; note your local store",
             "Low bot competition — product often lingers. Great MSRP fallback."),

    # --- Membership clubs ---
    PrepItem("sams-membership", "Sam's Club", "Have a Sam's membership ready for scheduled online drops",
             "Scheduled drops route through a short (~10–15 min) queue; limit ~2/membership."),
    PrepItem("costco-membership", "Costco", "Have a Costco membership; watch for warehouse/online bundles",
             "Bundles are warehouse-only, usually no restock — the first drop is the shot."),

    # --- GameStop: walk-in only now ---
    PrepItem("gamestop-instore", "GameStop", "Plan for in-store walk-in (TCG preorders discontinued Feb 2025)",
             "Ships direct to stores now; limit 2/customer (5 on single packs)."),
]


def _prep_path() -> Path:
    return data_dir() / "prep.json"


def load_done() -> set[str]:
    p = _prep_path()
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except (json.JSONDecodeError, OSError):
        return set()


def save_done(done: set[str]) -> None:
    _prep_path().write_text(json.dumps(sorted(done), indent=2))


def mark(item_id: str, done: bool = True) -> bool:
    ids = {i.id for i in PREP_ITEMS}
    if item_id not in ids:
        return False
    current = load_done()
    if done:
        current.add(item_id)
    else:
        current.discard(item_id)
    save_done(current)
    return True

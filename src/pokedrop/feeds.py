"""Community feed watchers.

Reddit's r/PokemonTCGDeals is the single best legitimate early-warning that a
preorder or restock just went live at an MSRP retailer. This never touches a
retailer's anti-bot layer — it reads a public Reddit feed via Reddit's own API.

Access paths, in order of reliability:
  1. OAuth (recommended): if a free "installed app" client_id is configured, we
     fetch a userless bearer token and call oauth.reddit.com. Reliable, higher limits.
  2. Public JSON fallback: www.reddit.com then old.reddit.com /new.json. These are
     increasingly rate-limited/blocked, so OAuth is preferred.
If everything is blocked, we degrade quietly (no crash) — date reminders still work.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timezone

import requests

from .config import RedditFeedSettings
from .models import AlertEvent
from .state import now_iso, parse_iso

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
INSTALLED_GRANT = "https://oauth.reddit.com/grants/installed_client"


def _device_id(feed_state: dict) -> str:
    did = feed_state.get("device_id")
    if not did:
        did = "".join(random.choices(string.ascii_letters + string.digits, k=30))
        feed_state["device_id"] = did
    return did


def _bearer_token(cfg, feed_state, user_agent, session, timeout) -> str | None:
    """Return a cached or freshly-minted userless OAuth token, or None."""
    tok = feed_state.get("oauth", {})
    exp = parse_iso(tok.get("expires_at"))
    if tok.get("token") and exp and datetime.now(timezone.utc) < exp:
        return tok["token"]
    try:
        resp = session.post(
            TOKEN_URL,
            auth=(cfg.client_id, cfg.client_secret),
            data={"grant_type": INSTALLED_GRANT, "device_id": _device_id(feed_state)},
            headers={"User-Agent": user_agent},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        body = resp.json()
        token = body.get("access_token")
        ttl = int(body.get("expires_in", 3600))
    except (requests.RequestException, ValueError):
        return None
    if not token:
        return None
    # Refresh a little early.
    from datetime import timedelta
    feed_state["oauth"] = {
        "token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl - 120)).isoformat(),
    }
    return token


def _fetch_new(sub, session, user_agent, timeout, token) -> list | None:
    """Fetch a subreddit's newest posts; return the list of children or None."""
    if token:
        urls = [(f"https://oauth.reddit.com/r/{sub}/new",
                 {"Authorization": f"bearer {token}", "User-Agent": user_agent})]
    else:
        urls = [
            (f"https://www.reddit.com/r/{sub}/new.json", {"User-Agent": user_agent}),
            (f"https://old.reddit.com/r/{sub}/new.json", {"User-Agent": user_agent}),
        ]
    for url, headers in urls:
        try:
            resp = session.get(url, params={"limit": 25}, headers=headers, timeout=timeout)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            return resp.json()["data"]["children"]
        except (ValueError, KeyError, TypeError):
            continue
    return None


def poll_reddit(
    cfg: RedditFeedSettings,
    state: dict,
    user_agent: str,
    timeout: int = 20,
) -> list[AlertEvent]:
    """Return alerts for new matching posts across configured subreddits."""
    if not cfg.enabled:
        return []

    now = datetime.now(timezone.utc)
    feed_state = state.setdefault("reddit", {})
    seen: set[str] = set(feed_state.get("seen_ids", []))
    keywords = [k.lower() for k in cfg.match_keywords]
    events: list[AlertEvent] = []
    session = requests.Session()

    token = None
    if cfg.client_id:
        token = _bearer_token(cfg, feed_state, user_agent, session, timeout)

    for sub in cfg.subreddits:
        gate = feed_state.get("last_poll", {}).get(sub)
        last = parse_iso(gate)
        if last and (now - last).total_seconds() < cfg.min_interval_seconds:
            continue

        children = _fetch_new(sub, session, user_agent, timeout, token)
        feed_state.setdefault("last_poll", {})[sub] = now_iso()
        if children is None:
            continue

        for child in children:
            post = child.get("data", {})
            pid = post.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)  # mark seen even on non-match so we don't rescan forever
            haystack = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
            if keywords and not any(k in haystack for k in keywords):
                continue
            permalink = "https://www.reddit.com" + post.get("permalink", "")
            events.append(AlertEvent(
                kind="reddit",
                title=f"📣 r/{sub}: {post.get('title', '(no title)')[:200]}",
                message=(
                    f"Match in r/{sub} — could be a live preorder/restock link.\n"
                    f"Posted by u/{post.get('author', '?')}. Verify before buying.\n"
                    f"{post.get('url', '')}"
                ),
                url=permalink,
                watch_id=f"reddit:{sub}",
            ))

    feed_state["seen_ids"] = list(seen)[-500:]
    return events

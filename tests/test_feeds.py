import pokedrop.feeds as feeds
from pokedrop.config import RedditFeedSettings
from pokedrop.feeds import poll_reddit


def test_disabled_feed_makes_no_calls():
    assert poll_reddit(RedditFeedSettings(enabled=False), {"watches": {}}, "UA") == []


def _post(pid, title):
    return {"data": {"id": pid, "title": title, "author": "u",
                     "permalink": f"/r/x/{pid}", "url": f"http://x/{pid}"}}


def test_match_filter_and_dedup(monkeypatch):
    posts = [
        _post("a1", "30th Celebration ETB live at Target!"),
        _post("a2", "unrelated booster box deal"),
    ]
    monkeypatch.setattr(feeds, "_fetch_new", lambda *a, **k: posts)
    cfg = RedditFeedSettings(enabled=True, subreddits=["PokemonTCGDeals"],
                             match_keywords=["30th"], min_interval_seconds=0)
    state = {"watches": {}}

    events = poll_reddit(cfg, state, "UA")
    assert len(events) == 1
    assert "30th celebration" in events[0].title.lower()

    # Both posts recorded as seen -> a second poll yields nothing new.
    assert poll_reddit(cfg, state, "UA") == []
    assert set(state["reddit"]["seen_ids"]) == {"a1", "a2"}


def test_min_interval_gate(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(*a, **k):
        calls["n"] += 1
        return []

    monkeypatch.setattr(feeds, "_fetch_new", fake_fetch)
    cfg = RedditFeedSettings(enabled=True, subreddits=["PokemonTCGDeals"],
                             match_keywords=["30th"], min_interval_seconds=9999)
    state = {"watches": {}}
    poll_reddit(cfg, state, "UA")
    poll_reddit(cfg, state, "UA")  # within interval -> skipped
    assert calls["n"] == 1

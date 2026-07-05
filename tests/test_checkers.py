from pokedrop.checkers import check_bestbuy, check_page, check_target, check_watch
from pokedrop.config import Settings
from pokedrop.models import Status, Watch


class FakeResp:
    def __init__(self, status=200, text="", json_data=None):
        self.status_code = status
        self.text = text
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeSession:
    def __init__(self, resp):
        self._resp = resp

    def get(self, *args, **kwargs):
        return self._resp


def _page_watch(**kw):
    return Watch(id="p", name="x", retailer="B&N", url="http://x", source="page", **kw)


def test_page_in_stock():
    r = check_page(_page_watch(), FakeSession(FakeResp(text="<button>Add to Cart</button>")),
                   "UA", 10, None)
    assert r.status == Status.AVAILABLE


def test_page_out_of_stock():
    r = check_page(_page_watch(), FakeSession(FakeResp(text="<span>Sold Out</span>")),
                   "UA", 10, None)
    assert r.status == Status.OUT_OF_STOCK


def test_page_ambiguous_is_conservative():
    # Both signals present -> treat as OOS rather than cry wolf.
    r = check_page(_page_watch(), FakeSession(FakeResp(text="Add to Cart ... Sold Out")),
                   "UA", 10, None)
    assert r.status == Status.OUT_OF_STOCK
    assert "ambiguous" in r.detail


def test_page_block_status_not_evaded():
    r = check_page(_page_watch(), FakeSession(FakeResp(status=403)), "UA", 10, None)
    assert r.status == Status.BLOCKED


def test_target_requires_tcin():
    w = Watch(id="t", name="x", retailer="Target", url="http://x", source="target")
    r = check_target(w, FakeSession(FakeResp()), "UA", 10, "webkey")
    assert r.status == Status.ERROR and "tcin" in r.detail


def test_target_parses_availability():
    payload = {"data": {"product": {"fulfillment": {
        "shipping_options": {"availability_status": "IN_STOCK"}}}}}
    w = Watch(id="t", name="x", retailer="Target", url="http://x", source="target", tcin="123")
    r = check_target(w, FakeSession(FakeResp(json_data=payload)), "UA", 10, "webkey")
    assert r.status == Status.AVAILABLE


def test_bestbuy_requires_key_and_sku():
    w = Watch(id="b", name="x", retailer="Best Buy", url="http://x", source="bestbuy", sku="1")
    assert check_bestbuy(w, FakeSession(FakeResp()), "UA", 10, "").status == Status.ERROR
    w2 = Watch(id="b", name="x", retailer="Best Buy", url="http://x", source="bestbuy")
    assert check_bestbuy(w2, FakeSession(FakeResp()), "UA", 10, "key").status == Status.ERROR


def test_dispatch_reminder_does_no_io():
    w = Watch(id="r", name="x", retailer="PC", url="http://x", source="reminder")
    # session that would raise if used -> proves reminder path never touches network
    class Boom:
        def get(self, *a, **k):
            raise AssertionError("reminder source must not make requests")
    r = check_watch(w, Boom(), Settings(), None)
    assert r.status == Status.UNKNOWN and "reminder-only" in r.detail

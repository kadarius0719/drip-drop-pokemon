# Retailer API reference (availability / stock checks)

This documents the **read-only availability APIs** PokeDrop uses to know *when a
product is buyable*, so you can review exactly what the tool calls. Scope, restated:

- ✅ These are **stock/price/availability lookups**. That's the whole job — tell a
  human when to go buy, fast.
- ❌ None of these are checkout, cart, or account endpoints. PokeDrop does not
  automate purchasing, and this doc intentionally does not cover order submission,
  cart APIs, or anti-bot bypass. Automating checkout violates every one of these
  retailers' terms and gets orders cancelled / accounts banned — see README.

The practical reality per retailer is uneven: only **two** major MSRP retailers
(Best Buy, Target) expose an availability signal you can poll without fighting
anti-bot systems. For the rest, the legitimate signal is a date reminder, the
retailer's own newsletter/app alert, or a community feed — not an API.

---

## 1. Best Buy — Products & Stores API  ⭐ the clean one

The only fully **sanctioned, documented, free** availability API among these retailers.

- **Portal / signup:** https://developer.bestbuy.com/
- **API docs:** https://bestbuyapis.github.io/api-documentation/
- **Auth:** free API key, passed as `?apiKey=…`
- **Rate limits:** ~5 requests/second, 50,000 requests/day (per the docs)
- **Formats:** JSON or XML

### Products API — availability by SKU (what PokeDrop uses)

```
GET https://api.bestbuy.com/v1/products(sku=<SKU>)?apiKey=<KEY>&format=json
    &show=sku,name,onlineAvailability,orderable,regularPrice
```

Key fields:
| field | meaning |
|---|---|
| `onlineAvailability` | boolean — orderable online right now |
| `orderable` | string — `Available`, `PreorderNow`, `SoldOut`, `ComingSoon`, `BackOrder` |
| `regularPrice` | current price (verify it's MSRP) |
| `inStoreAvailability` | boolean — carried in stores |

Filter example (all Pokémon TCG products under $60, sorted newest):
```
GET https://api.bestbuy.com/v1/products(search=pokemon&categoryPath.name=Trading Cards*&regularPrice<60)?apiKey=<KEY>&format=json&sort=itemUpdateDate.desc
```

### Stores API — in-store stock near a ZIP

```
GET https://api.bestbuy.com/v1/products/<SKU>/stores.json?apiKey=<KEY>&postalCode=<ZIP>&storeId.in=…
```

PokeDrop's implementation: [`check_bestbuy()` in src/pokedrop/checkers.py](../src/pokedrop/checkers.py). Put your key in `settings.yaml → bestbuy.api_key`.

---

## 2. Target — RedSky aggregations API

RedSky is Target's **public web/app backend**. It isn't a signed-up developer
program — it's the same JSON the target.com PDP fetches, and Target has stated the
aggregated data is considered public. It works without anti-bot evasion, **but**
Target IP-throttles aggressive callers, so poll it sparingly (PokeDrop backs off on
any 4xx/5xx rather than pushing through).

- **No official docs** (it's an internal-but-public API). Community writeups:
  - Endpoint catalog: https://gist.github.com/LumaDevelopment (RedSky writeup)
  - Overview: search "Target RedSky API" — several scraping-guide references
- **Auth:** a `key=` query param (a long-lived public web key). Keys rotate
  occasionally; if checks start 401/403-ing, grab the current `key=` value from a
  target.com request in your browser's Network tab and set `settings.yaml → target.web_key`.

### Fulfillment by TCIN (what PokeDrop uses)

```
GET https://redsky.target.com/redsky_aggregations/v1/web/pdp_fulfillment_v1
    ?key=<WEB_KEY>&tcin=<TCIN>&is_bot=false&pricing_store_id=<STORE_ID>
```

Response path PokeDrop reads:
```
data.product.fulfillment.shipping_options.availability_status
   → IN_STOCK | PRE_ORDER_SELLABLE | LIMITED_STOCK | OUT_OF_STOCK | ...
```

- **TCIN** = the numeric product id in a Target URL (`/p/…/-/A-<TCIN>`).
- Related endpoints you'll see in dev tools: `product_summary_with_fulfillment_v1`
  (title/price + stock in one call), `product_fulfillment_v1` (store pickup by ZIP).

PokeDrop's implementation: [`check_target()` in src/pokedrop/checkers.py:117](../src/pokedrop/checkers.py#L117).

> Note: RedSky is undocumented and Target can change or gate it at any time. It's
> the shakiest of the availability sources; treat a block as "fall back to reminders."

---

## 3. Reddit — r/PokemonTCGDeals feed (the best early-warning)

Not a retailer, but the highest-signal *legit* "it just went live somewhere" source.
Reddit has a real, sanctioned API with a free tier.

- **API docs:** https://www.reddit.com/dev/api/
- **OAuth guide:** https://github.com/reddit-archive/reddit/wiki/OAuth2
- **Create an app (free):** https://www.reddit.com/prefs/apps  → type **installed app**
- **Rate limits:** ~100 requests/min with OAuth; unauthenticated is ~1/min and often blocked

### Endpoints PokeDrop uses

```
# userless OAuth token (installed app; client_secret blank)
POST https://www.reddit.com/api/v1/access_token
     grant_type=https://oauth.reddit.com/grants/installed_client&device_id=<id>

# newest posts
GET  https://oauth.reddit.com/r/PokemonTCGDeals/new?limit=25   (Authorization: bearer <token>)
# public fallback (often 403 on datacenter IPs):
GET  https://www.reddit.com/r/PokemonTCGDeals/new.json?limit=25
```

PokeDrop's implementation: [`src/pokedrop/feeds.py`](../src/pokedrop/feeds.py). Set
`settings.yaml → reddit_feed.client_id`.

---

## 4. Catalog metadata APIs (know a product *exists* + its ids)

These don't give retailer stock, but they tell you when a new sealed product/set
appears so you know what to watch for. Both are built for polite polling.

- **Pokémon TCG API** — https://pokemontcg.io/ · docs https://docs.pokemontcg.io/
  - `GET https://api.pokemontcg.io/v2/sets` and `/cards` (JSON; free, optional key)
- **TCGCSV** — https://tcgcsv.com/ — nightly mirror of TCGplayer catalog + prices as
  CSV/JSON (good for spotting new sealed SKUs and MSRP-vs-market movement)

---

## 5. Retailers with **no** sanctioned availability API

For these, there is no clean public endpoint — reaching stock status means going
through an anti-bot layer, which is out of scope. The legitimate signal is listed
for each. PokeDrop tracks all of these as `source: reminder`.

| Retailer | Why no API path | Legit signal to use instead |
|---|---|---|
| **Pokémon Center** | Queue-it randomized virtual queue + DataDome/Imperva/hCaptcha; no public product API | Email newsletter (drops open ~78 days early, quietly); date reminders |
| **Walmart** | PerimeterX / HUMAN "Press & Hold"; dev APIs are supplier-only | Walmart app "notify me"; community feeds; reminders |
| **GameStop** | Storefront returns 403 to automated fetch; TCG preorders discontinued Feb 2025 | In-store walk-in; .com restock reminders |
| **Costco / Sam's Club** | Membership-gated; no product API | Sam's scheduled-drop pages + queue; membership + reminders |
| **Barnes & Noble** | No public API, but **low** bot protection | Polite product-page check (`source: page`) is viable here |
| **Amazon** | PA-API is affiliate-gated, throttled, closed to new signups, deprecating 2026 | Not an MSRP source anyway — skip |
| **Local game stores** | Individual shops (Crystal Commerce/BinderPOS); no unified API | **Call/email to preorder** — the best MSRP shot, zero bot race |

---

## The tactic that actually wins boxes for a human

Since the frustration is real, here's where the odds actually live — none of it
requires automating a purchase:

1. **Win the "knowing" race.** Alerts in the first seconds (Best Buy API + Target
   RedSky + the Reddit feed) beat finding out minutes late. That's 90% of it.
2. **Pre-stage checkout.** Account created, payment + shipping saved, logged in on
   the phone app (Target's app checks out faster than the site). Aim for a
   sub-30-second manual checkout.
3. **Spread across retailers.** The people who get boxes buy the *calm* channels:
   **LGS preorders** and **Barnes & Noble** rarely sell out in seconds. One LGS
   preorder is worth more than ten frantic Target refreshes.
4. **Pokémon Center newsletter + queue readiness.** Its queue is *randomized*, not
   first-come — so bots don't actually help there; being in the queue at all is what
   matters. No VPN/ad-blocker at checkout (they trip its anti-bot).
5. **Buy over the whole wave.** The 30th Celebration line drops Sept 16 → Dec 4.
   Restocks are common in the weeks after launch; you don't have to win day one.

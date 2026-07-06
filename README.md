# PokeDrop

[![CI](https://github.com/kadarius0719/drip-drop-pokemon/actions/workflows/ci.yml/badge.svg)](https://github.com/kadarius0719/drip-drop-pokemon/actions/workflows/ci.yml)

A personal **drop tracker + alert-and-prep** tool for Pokémon TCG releases — built
first for the **30th Celebration** line (global launch **Sept 16, 2026**).

📖 **New here? Start with the [User Guide](docs/USER_GUIDE.md)** — every feature
explained with real screenshots. API details live in [docs/APIS.md](docs/APIS.md).

![The PokeDrop live dashboard](docs/images/tui-main.svg)

It tells *you* the moment a preorder/restock goes live and helps you be ready to
check out fast at MSRP retailers. **You** make every purchase, by hand.

## What it does (and deliberately does not)

**Does**
- Tracks the confirmed 30th Celebration lineup with dates, MSRP, and per-retailer notes.
- **Date reminders** — pings you at 24h / 1h / 10min before a drop. Pure local
  scheduling; never touches a retailer. This is the reliable backbone.
- **Live stock checks** at the two retailers with sanctioned/public data paths:
  **Best Buy** (free developer API) and **Target** (public RedSky fulfillment API).
- **Community early-warning** — polls Reddit `r/PokemonTCGDeals` public JSON feed for
  posts about the 30th set (the best legit "it just went live somewhere" signal).
- **Alerts to Discord + email**, each with the direct product link.
- **Prep checklist** — the account/payment/where-to-buy prep that wins MSRP drops.
- An **HTML dashboard** and a CLI status table.

**Does not — by design**
- ❌ No adding to cart, no checkout, no placing orders.
- ❌ No creating accounts for you.
- ❌ No evading anti-bot systems, CAPTCHAs, queues, or rate limits. If a retailer
  blocks an automated check (403/429/queue), the tool backs off and relies on date
  reminders. Heavily protected sites (Pokémon Center, Walmart, GameStop) are
  **reminder-only** on purpose.

These limits are the point. Automated purchasing violates retailer terms, invites
legal exposure (anti-"Grinch-bot" laws, computer-access laws), and is the mechanism
behind scalping. This tool keeps a human in the loop.

## Setup

A virtualenv is already set up at `.venv` with dependencies installed, and the config
files already exist. If you're starting fresh (new machine / deleted venv):

```bash
cd /Users/beaumorton/code/vibes/pokemon_drop
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt

./.venv/bin/python run.py init   # creates config/settings.yaml + config/watchlist.yaml
```

All commands below use `./.venv/bin/python`. If you prefer plain `python`, activate the
venv first: `source .venv/bin/activate`.

Then edit `config/settings.yaml`:

1. **Discord** — in your server: *Server Settings → Integrations → Webhooks → New
   Webhook → Copy URL*. Paste into `alerts.discord.webhook_url` and set `enabled: true`.
2. **Email** — for Gmail, enable 2FA then create an **App Password**
   (myaccount.google.com → Security → App passwords). Put your address in `username`
   /`from_addr`, the app password in `password`, your inbox in `to_addrs`, `enabled: true`.
3. **Best Buy** (optional, recommended) — grab a free key at
   https://developer.bestbuy.com/ and set `bestbuy.api_key`.
4. **Reddit** (optional, recommended) — unauthenticated Reddit access is often
   blocked. Create a free app at https://www.reddit.com/prefs/apps (type *installed
   app*), and paste its `client_id` into `reddit_feed.client_id` (secret stays blank).

Verify the channels:

```bash
./.venv/bin/python run.py test-alerts
```

## Usage

```bash
./.venv/bin/python run.py ui              # ⭐ live auto-updating dashboard (TUI)
./.venv/bin/python run.py status          # watchlist + current status + prep progress
./.venv/bin/python run.py check           # run one pass now (fires alerts on changes)
./.venv/bin/python run.py check --no-alerts   # dry run, just print what it sees
./.venv/bin/python run.py watch           # run continuously (Ctrl-C to stop)
./.venv/bin/python run.py dashboard       # write data/dashboard.html
./.venv/bin/python run.py prep            # show the prep checklist
./.venv/bin/python run.py prep --done lgs-preorder   # tick an item off
./.venv/bin/python run.py list            # list configured watches
```

### The live dashboard (TUI)

`./.venv/bin/python run.py ui` opens an always-on terminal dashboard:

- **Drop-event tabs** (`[` / `]` to switch) — one tab per release wave, defined in
  the watchlist's `events:` section. Tabs filter the view only; monitoring and
  alerts always cover every tab.
- **Watchlist** with per-product countdowns ticking every second and live statuses.
- **Event feed** at the bottom — availability alerts, reminders, and Reddit matches
  appear as they happen (persisted to `data/events.jsonl`).
- **Topline** shows the next drop, when the next check runs, and which alert
  channels are enabled.
- The monitor engine runs *inside* the TUI on your configured interval, so don't
  run the `watch` daemon at the same time (you'd get duplicate alerts).

Keys: `c` check now · `o` open selected product in browser · `p` prep checklist
(Enter toggles items) · `q` quit.

Native macOS Notification Center pop-ups are on by default (`alerts.macos.enabled`
in settings.yaml) and work in both the TUI and the daemon.

### Run it in the background (macOS launchd)

```bash
cp scripts/com.pokedrop.monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.pokedrop.monitor.plist   # starts + auto-restarts
launchctl unload ~/Library/LaunchAgents/com.pokedrop.monitor.plist # stop
```

Logs go to `data/monitor.log`. (Cron alternative: run
`./.venv/bin/python run.py check` every few minutes.)

## The watchlist

`config/watchlist.yaml` is seeded with all 15 confirmed 30th Celebration products as
**reminder** watches, so date alerts work immediately. It also includes disabled
**live-check templates** for Target / Best Buy / Barnes & Noble — once a retailer
publishes its preorder page, fill in the `tcin` (Target), `sku` (Best Buy), or product
`url` (B&N), set `enabled: true`, and that product gets real stock polling too.

Set a watch's `drop_time` to the actual **preorder open** datetime once a retailer
announces it — that's when the 24h/1h/10min reminders will fire.

## Where the MSRP shots actually are (from research)

| Retailer | MSRP? | Live check | Notes |
|---|---|---|---|
| Local game store | ✅ | manual | **Best shot** — preorder in person, no bot race |
| Barnes & Noble | ✅ | `page` | Low competition "hidden gem"; product lingers |
| Best Buy | ✅ | `bestbuy` API | Sanctioned free API; Tue/Thu AM restocks |
| Target | ✅ | `target` RedSky | App checks out fastest; Sun/Mon in-store |
| Pokémon Center | ✅ | reminder-only | First-party, but randomized Queue-it on hype |
| Walmart | ✅ (1st-party) | reminder-only | PerimeterX; keep qty 1–2 |
| Sam's Club / Costco | ✅ | reminder-only | Membership; scheduled/warehouse drops |
| GameStop | ✅ | reminder-only | Walk-in only (preorders ended Feb 2025) |
| Amazon | ⚠️ often > MSRP | — | Excluded as an MSRP source |

Run `python run.py prep` for the full, tickable checklist.

For the actual API details behind the live checks (Best Buy, Target RedSky, Reddit,
catalog APIs) plus an honest per-retailer breakdown, see [docs/APIS.md](docs/APIS.md).

## Project layout

```
run.py                     # entrypoint: python run.py <command>
config/
  settings.example.yaml    # copy -> settings.yaml (secrets; git-ignored)
  watchlist.example.yaml   # copy -> watchlist.yaml (the 30th Celebration lineup)
src/pokedrop/
  cli.py        # commands
  config.py     # config + watchlist loading/validation
  models.py     # Watch / CheckResult / AlertEvent
  checkers.py   # source adapters: page / target / bestbuy (+ robots, backoff)
  feeds.py      # Reddit r/PokemonTCGDeals feed watcher
  reminders.py  # date-based reminders
  engine.py     # the run loop + event log (data/events.jsonl)
  alerts.py     # Discord + email + macOS notification dispatch
  dashboard.py  # HTML + CLI rendering
  tui.py        # live terminal dashboard (Textual)
  prep.py       # prep checklist
scripts/
  com.pokedrop.monitor.plist   # launchd background service
```

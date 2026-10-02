# Kalshi Manual-Strategy Bot

Automates a trading strategy reverse-engineered from the owner's manual Kalshi
trading history: scan every open market, take the high-probability side of
anything that qualifies, size each position as a percentage of the account,
and diversify across as many qualifying markets as show up per day. Includes
a local web dashboard that mirrors the owner's own trade-tracking spreadsheet.

## How it's put together

```
main.py                        CLI entrypoint (paper or live mode)
kalshi_bot/
  client.py                    Kalshi REST client (RSA-PSS/Ed25519 request signing)
  auth.py                      Request signing
  config.py                    Env-driven settings, risk limits, strategy params
  risk.py                      Hard limits enforced on every trade regardless of strategy
  sizing.py                    Converts a target % of equity into a contract count
  ledger.py                    SQLite ledger: deposits + trade log, dashboard/daily aggregation
  strategy/
    base.py                    MarketSnapshot / TradeSignal data model
    manual_replica.py          The actual entry-rule strategy
  engine/
    discovery.py                Pages through every open market on Kalshi
    naming.py                   Resolves a human-readable title for a traded market
    settlement.py                Marks ledger trades Won/Lost once Kalshi resolves them
    runner.py                    Ties it together: scan -> signal -> size -> risk check -> execute
    paper.py / live.py           The two Broker implementations
dashboard/
  server.py                    Flask app serving the ledger as JSON + the dashboard page
  static/index.html            The dashboard itself (vanilla JS, no build step)
tests/                         pytest, no network calls -- fakes/in-memory SQLite throughout
launchd/                       macOS LaunchAgent plists (run continuously on this machine)
deploy/                        Provisioning + systemd units for running on a Linux VPS instead
```

## The strategy (`kalshi_bot/strategy/manual_replica.py`)

A market qualifies when, on a given poll:
- it's binary (yes/no), not scalar
- it settles within `MAX_HOURS_TO_CLOSE` (default 24h) but not sooner than
  `MIN_MINUTES_TO_CLOSE` (default 5min, so there's time to fill/track it)
- one side (yes or no) is priced in `[MIN_PROBABILITY, MAX_PROBABILITY]`
  (default 0.90-0.99 -- the ceiling excludes prices with no real margin
  left, e.g. exactly $1.00, which nets $0 even on a win once fees are counted)

No category allowlist by design -- it scans the whole open-markets list every
pass rather than a fixed ticker list or financial-only filter, a deliberate
choice to gather broad data before narrowing scope.

This was reverse-engineered from a 156-trade manual log: ~94.5% win rate,
buying 0.90-0.99c yes/no contracts 30min-3hrs before same-day settlement.
Two things worth remembering while tuning this:
- The historical win rate sat almost exactly at the average entry price
  (95.45% wins vs. 95.2% avg implied probability) -- the edge is real but
  thin, not a mispricing to lean on heavily.
- The highest-confidence price band (0.96-0.99c) was actually the *worst*
  band by dollars in that sample, because a handful of losses clustered
  there. Small sample, so not decisive -- but it's why sizing is capped
  per-trade regardless of how "safe" a given price looks.

One important mechanical detail: Kalshi's order API only ever quotes prices
in yes-terms. Buying "no" means placing a sell-yes order at `yes_bid`, but
the real cost per contract is `no_ask` (often ~50-100x larger than
`yes_bid`). `TradeSignal` carries both `limit_price` (what's sent to the
API) and `true_price` (the real cost, used for sizing/risk/ledger) to keep
these from being conflated -- an earlier version of this bug sized "buy no"
trades as if they cost pennies when they actually cost most of a dollar.

## Risk controls (`kalshi_bot/risk.py`)

All limits are **fractions of current account equity**, so they scale as the
balance grows or shrinks, and are enforced on every signal regardless of
what the strategy proposes:

- `POSITION_FRACTION` (default 3%) -- target stake per trade
- `MAX_POSITION_FRACTION` (default 8%) -- hard per-trade ceiling
- `MAX_TOTAL_EXPOSURE_FRACTION` (default 60%) -- cap on money committed
  across all simultaneously-open positions
- `MAX_DAILY_LOSS_FRACTION` (default 15%) -- halts new trades once today's
  drawdown from day-start equity hits this
- `MAX_OPEN_POSITIONS` (default 25)

Plus one rule enforced in `Runner` itself: **at most one open position per
underlying event at a time.** Multiple strikes on the same event (e.g. ten
different WTI oil price thresholds for the same day) are correlated bets,
not independent diversification, even though Kalshi exposes them as
separate markets/tickers.

**Kill switch:** create a file named `STOP` in the project root (`touch
STOP`) to halt all trading, paper or live, on the next poll. Delete it and
restart the process to resume. (If running under the `launchd`/`systemd`
services below, a clean kill-switch exit is intentionally *not*
auto-restarted -- see Running continuously.)

## Setup

1. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. Generate a key pair. Ed25519 is preferred but needs OpenSSL 3+ (macOS
   ships LibreSSL, which doesn't support it) -- RSA-2048 works everywhere
   and is what `kalshi_bot/auth.py` supports either way:
   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out kalshi_private_key.pem
   openssl pkey -in kalshi_private_key.pem -pubout -out kalshi_public_key.pem
   ```
   (Kalshi may instead generate the key pair for you and hand you a private
   key to download when you create an API key in its UI -- either flow
   works, just save whichever private key you end up with as
   `kalshi_private_key.pem`.)
3. Go to your Kalshi account's API Keys settings and register the **public**
   key. Never paste the private key anywhere outside this project.
4. `cp .env.example .env` and fill in `KALSHI_API_KEY_ID` and
   `KALSHI_PRIVATE_KEY_PATH`. `KALSHI_ENV` must match whichever Kalshi
   account (demo sandbox vs. real) the key was generated on.
5. Verify auth works (read-only, places no orders):
   ```bash
   python scripts/check_auth.py
   ```

## Running

```bash
# Paper mode: simulated fills, no real orders placed. Still reads real
# market data and seeds its simulated cash from the real account balance
# on first run, so sizing decisions are realistic.
python main.py --mode paper --interval 30

# Live mode: places real orders. Only after paper testing looks right.
python main.py --mode live --interval 30
```

Add `--once` to run a single pass instead of looping.

## Dashboard (`dashboard/`)

A local web UI over the shared ledger, mirroring the four sheets of the
owner's original tracking spreadsheet: a KPI row + cumulative balance chart,
a day-by-day summary, the full trade log (with a human-readable market
title, not just the raw ticker), and deposits (with a form to log new
ones -- Kalshi doesn't expose bank deposits via API).

```bash
python dashboard/server.py
# open http://localhost:8765
```

It's a separate process from `main.py` -- both read/write the same
`ledger.db`, so the dashboard can stay open while the bot runs. Every trade
is logged the instant it's placed (status "Open"), then flipped to
Won/Lost once Kalshi actually resolves the market -- checked every polling
cycle by `kalshi_bot/engine/settlement.py`, which works in paper mode too
since paper trades track real market outcomes, they just never place a real
order. Use the Mode selector to view paper vs. live trades separately or
combined.

## Running continuously

A one-off `python main.py` dies when the terminal closes. Two options,
already set up:

**macOS, via `launchd`** (`launchd/*.plist`): survives terminal/session
close and reboots (as long as you're logged in), auto-restarts on crash,
and *won't* resurrect a deliberate kill-switch stop. Install:
```bash
cp launchd/*.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kalshi.bot.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kalshi.dashboard.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kalshi.watchdog.plist
```
After editing any `.py` file, the running service needs an explicit restart
to pick it up (Python doesn't hot-reload):
```bash
launchctl kickstart -k gui/$(id -u)/com.kalshi.bot
launchctl kickstart -k gui/$(id -u)/com.kalshi.dashboard
```
**Important caveat:** a `launchd` agent only runs while the *Mac itself* is
awake. Closing the laptop lid puts the whole machine to sleep, which pauses
everything -- bot, dashboard, watchdog -- until it's opened again. It
resumes cleanly on wake (nothing crashes or needs manual restart), but
there's a monitoring/trading gap for however long it slept. Clamshell mode
(power + an external display) avoids this; a VPS avoids it entirely.

**Linux VPS, via `systemd`** (`deploy/`): for genuinely unattended
operation independent of any laptop's power state.
```bash
deploy/provision.sh            # one-time, run on a fresh Ubuntu 24.04 box
deploy/push_credentials.sh <ip>  # one-time, pushes .env + private key, locked to 600
deploy/sync_and_deploy.sh <ip>   # any time you push a code change
```
The dashboard binds `127.0.0.1` on the VPS too -- reach it via an SSH
tunnel (`ssh -L 8765:localhost:8765 root@<ip>`), not by opening the port.

## Testing

```bash
python -m pytest tests/ -q
```
No network calls in the test suite -- brokers/clients are faked and the
ledger uses a temp SQLite file per test.

## Notes / known limitations

- Endpoints and the auth scheme were pulled from live docs.kalshi.com
  (Sept/Oct 2026) and cross-checked against real API responses in several
  places where the docs turned out to be wrong or incomplete (e.g. a
  resolved market's `status` is `finalized`, not `settled` as the
  docs' filter-parameter enum implied). If a call starts failing, check
  https://docs.kalshi.com/api-reference first, but verify against a real
  response rather than trusting it blindly.
- The market scanner pages through every open market closing within the
  configured window (deliberately no category filter), so a very active
  day means a lot of API calls per poll -- watch `logs/bot.log`'s heartbeat
  line ("scanned N markets") if you ever hit rate limits.
- `ledger.db`, `.env`, and `*.pem` are gitignored and never committed.

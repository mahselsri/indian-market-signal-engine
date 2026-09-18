# Signal Engine (Stage 1 of the Indian-market pipeline)

Scans a universe of Indian equities, computes technical indicators, and
scores/ranks candidates. This is the piece that sits right after "Market
Data" and right before "GROQ AI" in the full pipeline:

```
Market Data -> [SIGNAL ENGINE] -> Candidates -> GROQ AI -> Paper Trader -> Dashboard
```

## Setup

```bash
git clone https://github.com/mahselsri/indian-market-signal-engine.git
cd indian-market-signal-engine
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste in your ALPHA_VANTAGE_API_KEY
```

## Run

```bash
python main.py --universe watchlist --top 5
python main.py --universe nifty50 --top 10
```

Output: a ranked table in your terminal, plus a JSON file under
`output/signals_<timestamp>.json` — this file is the handoff point for the
Groq AI stage (each candidate carries its indicator values AND a list of
plain-English reasons, so an LLM prompt doesn't need to recompute anything,
just interpret/validate).

## Important limitations (free tier realities)

1. **Alpha Vantage's free API key is heavily rate-limited** — 25
   requests/day, and only `outputsize=compact` (last ~100 daily bars) is
   available; requesting `full` history is a premium-only parameter and
   every such request gets rejected outright (this bit us once already —
   see the fix history in this repo). This code always requests `compact`
   and paces requests out with a minimum gap between calls. Scanning all
   of NIFTY 50 (50 symbols) will still exceed a 25/day quota in one run.
   Options:
   - Use `--universe watchlist` (10 symbols) while developing/testing.
   - Split a full NIFTY50/100 scan across multiple days.
   - Upgrade to a paid Alpha Vantage plan, or move to Zerodha's Kite
     Connect API (near real-time, much higher limits, but paid + needs a
     Zerodha trading account) — see "Swapping data sources" below.
   - Responses are cached to disk for the current calendar day
     (`.cache/`), so re-running the same universe on the same day doesn't
     spend additional quota.

2. **No true intraday VWAP.** Alpha Vantage's free tier daily bars don't
   support session VWAP. `indicators.vwap_proxy()` computes a rolling
   N-day volume-weighted average price instead — a reasonable "value
   area" reference, but not the same thing as intraday VWAP. Once you're
   on Zerodha or a paid intraday feed, add a real `intraday_vwap()`
   function and wire it in.

3. **Index constituent lists drift.** `symbols.py` hardcodes NIFTY 50/100
   membership as of when this was written. Refresh it periodically from
   the NSE's official index sheet before relying on it for live use.

4. **Relative strength benchmark.** By default (no `BENCHMARK_SYMBOL` set)
   relative strength is measured against the equal-weighted average
   return of whatever was successfully scanned this run — a pragmatic
   stand-in for "the market" given that Alpha Vantage doesn't cleanly
   expose NSE index levels on the free tier. Set `BENCHMARK_SYMBOL` in
   `.env` if you find an AV symbol that works for your index of choice.

## Swapping data sources later (Zerodha / yfinance)

Every indicator and the scoring logic only depend on
`DataFetcher.get_daily_ohlcv(symbol) -> DataFrame[open, high, low, close, volume]`.
To move to Zerodha's Kite Connect:

1. Add a `ZerodhaFetcher(DataFetcher)` class in `data_fetcher.py`
   implementing that one method (Kite gives you real intraday data too,
   so you could add `get_intraday_ohlcv()` for a true VWAP at the same
   time).
2. Register it in `get_fetcher()`.
3. Set `DATA_SOURCE=zerodha` in `.env`.

Nothing in `indicators.py`, `signal_engine.py`, or `main.py` needs to
change.

## Files

- `config.py` — all tunables (thresholds, rate limits, universe choice)
- `symbols.py` — NIFTY 50 / 100 / watchlist symbol lists
- `data_fetcher.py` — Alpha Vantage client, rate limiter, disk cache
- `indicators.py` — VWAP proxy, RSI, ATR, breakout, relative strength
- `signal_engine.py` — orchestration + rule-based scoring
- `main.py` — CLI entry point
- `test_offline.py` — smoke test with synthetic data (no API calls)

## Pushing to GitHub

Files live at the repo root (no `signal_engine/` subfolder) — `config.py`,
`main.py`, `.github/`, etc. are all siblings.

```bash
cd indian-market-signal-engine   # the folder you unzipped, containing config.py, main.py, .github/, etc.
git init
git add .
git commit -m "Initial commit: signal engine"
git branch -M main
git remote add origin https://github.com/mahselsri/indian-market-signal-engine.git
git push -u origin main
```

## Running on a schedule with GitHub Actions (recommended for this stage)

A workflow is already included at `.github/workflows/scan.yml`. It runs
Mon–Fri at 4:00 PM IST (30 min after NSE close), scans the configured
universe, and commits the resulting `output/signals_*.json` back into the
repo — so your data updates automatically without any server to manage.

To enable it:

1. Push this repo to GitHub (see above).
2. In the repo, go to **Settings → Secrets and variables → Actions → New
   repository secret** and add:
   - `ALPHA_VANTAGE_API_KEY` = your Alpha Vantage key
   - (later) `GROQ_API_KEY` = your Groq key, once the AI stage is built
3. Optional: under **Settings → Secrets and variables → Actions → Variables**,
   add a `UNIVERSE` variable set to `nifty50` or `nifty100` once you're
   ready to move past the watchlist (mind the daily call budget — see the
   limitations section above).
4. Go to the **Actions** tab and confirm the "Daily Signal Scan" workflow
   is enabled. You can also trigger it manually via **Run workflow**
   (`workflow_dispatch`) to test it immediately rather than waiting for
   the schedule.

Each run's `output/signals_<timestamp>.json` lands in your repo's git
history — which is exactly the file a Vercel-hosted dashboard can fetch
and render (e.g. via `raw.githubusercontent.com`, or by having the
dashboard's own build pull from the repo).

## Where Vercel fits

Don't deploy *this* scanning script to Vercel — it's a scheduled batch
job with local disk caching and rate-limiting, which doesn't suit
Vercel's stateless, time-limited serverless functions. Vercel is the
right tool for the **Next.js dashboard**, the last box in the pipeline
diagram: a separate Next.js project in the same GitHub repo (or a
sibling repo) that reads the JSON this workflow produces and renders it.
When we build that stage, connecting it to Vercel is a one-click "Import
Git Repository" from your Vercel dashboard, no extra config needed for
a static/SSR JSON-reading app.

## Next steps (later stages, not built yet)

- **Groq AI stage**: feed each `Candidate.to_dict()` (or the saved JSON)
  to `openai/gpt-oss-120b` via Groq's API, asking it to validate/score
  the setup and produce a plain-English explanation.
- **Paper trader**: consume the AI-scored candidates, simulate
  entry/stop/target and track P&L.
- **Next.js dashboard**: read the pipeline's JSON output(s) and render
  live tables/charts.

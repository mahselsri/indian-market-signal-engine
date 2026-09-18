"""
Central configuration for the Signal Engine.

All secrets are read from environment variables (or a local .env file via
python-dotenv) — never hardcode API keys here.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # loads variables from a .env file in the working directory, if present


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")  # used by the next stage (AI analysis)
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------
# "alpha_vantage" today; "zerodha" / "yfinance" can be added later behind the
# same DataFetcher interface (see data_fetcher.py).
DATA_SOURCE = os.getenv("DATA_SOURCE", "alpha_vantage")

# Alpha Vantage free-tier limits (change if you're on a paid plan)
AV_CALLS_PER_MINUTE = int(os.getenv("AV_CALLS_PER_MINUTE", "5"))
AV_CALLS_PER_DAY = int(os.getenv("AV_CALLS_PER_DAY", "25"))

# How many daily bars to pull per symbol. Alpha Vantage's free tier only
# supports outputsize=compact (last ~100 daily bars) — "full" history is a
# premium-only parameter and every request with it gets rejected. 100 bars
# is comfortably enough for 14/20-period indicators, so don't raise this
# above ~100 unless you've upgraded your Alpha Vantage plan.
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "100"))

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
# "nifty50", "nifty100", or "watchlist" (small custom list — good for
# testing without burning your daily AV quota)
UNIVERSE = os.getenv("UNIVERSE", "watchlist")

# Optional benchmark symbol (e.g. a Nifty index ETF that Alpha Vantage can
# actually quote, such as "NIFTYBEES.BSE"). Leave blank to fall back to
# "average return of the scanned universe" as the relative-strength benchmark.
BENCHMARK_SYMBOL = os.getenv("BENCHMARK_SYMBOL", "")

# ---------------------------------------------------------------------------
# Indicator / signal thresholds — tune these freely
# ---------------------------------------------------------------------------
RSI_PERIOD = 14
ATR_PERIOD = 14
VWAP_WINDOW = 20            # "N-day VWAP" proxy window (no intraday data on free tier)
BREAKOUT_LOOKBACK = 20      # N-day high/low breakout window
VOLUME_SURGE_LOOKBACK = 20  # window for average-volume comparison
VOLUME_SURGE_RATIO = 1.5    # today's volume must be >= this x the N-day average
RSI_MIN = 40                # avoid deeply oversold names
RSI_MAX = 70                # avoid deeply overbought names
RELATIVE_STRENGTH_LOOKBACK = 20  # trading days

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CACHE_DIR = os.getenv("CACHE_DIR", ".cache")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

"""
Data fetching layer.

Design goal: everything above this file (indicators, signal_engine) only
talks to `DataFetcher.get_daily_ohlcv(symbol)` and gets back a pandas
DataFrame with columns [open, high, low, close, volume], indexed by date,
oldest first. That means swapping Alpha Vantage for Zerodha's Kite Connect
or yfinance later is a matter of writing a new class with the same method
and changing config.DATA_SOURCE — nothing else in the pipeline changes.
"""

from __future__ import annotations

import json
import time
import os
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timedelta

import pandas as pd
import requests

from . import config


class RateLimiter:
    """Simple sliding-window rate limiter for calls-per-minute AND a hard
    calls-per-day cap, so a scan over a big universe fails fast and loudly
    instead of silently eating your daily quota with error responses."""

    def __init__(self, calls_per_minute: int, calls_per_day: int):
        self.calls_per_minute = calls_per_minute
        self.calls_per_day = calls_per_day
        self._minute_window: deque = deque()
        self._day_count = 0
        self._day_started = datetime.now().date()

    def _roll_day(self):
        today = datetime.now().date()
        if today != self._day_started:
            self._day_started = today
            self._day_count = 0

    def wait_for_slot(self):
        self._roll_day()
        if self._day_count >= self.calls_per_day:
            raise RuntimeError(
                f"Daily Alpha Vantage call budget ({self.calls_per_day}) exhausted. "
                "Reduce your universe size, wait until tomorrow, or upgrade your plan."
            )

        now = time.monotonic()
        while self._minute_window and now - self._minute_window[0] > 60:
            self._minute_window.popleft()

        if len(self._minute_window) >= self.calls_per_minute:
            sleep_for = 60 - (now - self._minute_window[0]) + 0.1
            if sleep_for > 0:
                time.sleep(sleep_for)

        self._minute_window.append(time.monotonic())
        self._day_count += 1


class DiskCache:
    """Caches raw API responses to disk for one calendar day, keyed by
    symbol. Avoids re-spending your rate-limited quota on repeat runs
    while you're iterating on indicator logic."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe_key = key.replace("/", "_")
        today = datetime.now().strftime("%Y%m%d")
        return os.path.join(self.cache_dir, f"{safe_key}_{today}.json")

    def get(self, key: str):
        path = self._path(key)
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return None

    def set(self, key: str, value):
        path = self._path(key)
        with open(path, "w") as f:
            json.dump(value, f)


class DataFetcher(ABC):
    @abstractmethod
    def get_daily_ohlcv(self, symbol: str) -> pd.DataFrame:
        """Return a DataFrame indexed by date (ascending) with columns
        [open, high, low, close, volume]."""
        raise NotImplementedError


class AlphaVantageFetcher(DataFetcher):
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.ALPHA_VANTAGE_API_KEY
        if not self.api_key:
            raise ValueError(
                "No Alpha Vantage API key set. Put ALPHA_VANTAGE_API_KEY in your "
                "environment or a .env file."
            )
        self.rate_limiter = RateLimiter(config.AV_CALLS_PER_MINUTE, config.AV_CALLS_PER_DAY)
        self.cache = DiskCache(config.CACHE_DIR)

    def get_daily_ohlcv(self, symbol: str) -> pd.DataFrame:
        cached = self.cache.get(symbol)
        if cached is not None:
            return self._parse_daily_response(cached, symbol)

        self.rate_limiter.wait_for_slot()

        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "full" if config.LOOKBACK_DAYS > 100 else "compact",
            "apikey": self.api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        if "Error Message" in payload:
            raise ValueError(f"Alpha Vantage error for {symbol}: {payload['Error Message']}")
        if "Note" in payload:
            # This is Alpha Vantage's way of saying "you're rate limited"
            raise RuntimeError(f"Alpha Vantage rate-limit note for {symbol}: {payload['Note']}")
        if "Information" in payload:
            # Free-tier premium-endpoint / quota messages land here too
            raise RuntimeError(f"Alpha Vantage info/limit message for {symbol}: {payload['Information']}")

        self.cache.set(symbol, payload)
        return self._parse_daily_response(payload, symbol)

    @staticmethod
    def _parse_daily_response(payload: dict, symbol: str) -> pd.DataFrame:
        series = payload.get("Time Series (Daily)")
        if not series:
            raise ValueError(f"No daily time series in Alpha Vantage response for {symbol}: {payload}")

        rows = []
        for date_str, values in series.items():
            rows.append({
                "date": datetime.strptime(date_str, "%Y-%m-%d"),
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": float(values["5. volume"]),
            })

        df = pd.DataFrame(rows).sort_values("date").set_index("date")
        cutoff = datetime.now() - timedelta(days=int(config.LOOKBACK_DAYS * 1.6))  # buffer for weekends/holidays
        df = df[df.index >= cutoff]
        return df


def get_fetcher() -> DataFetcher:
    """Factory — swap DATA_SOURCE in config.py (and add a class above) to
    move to Zerodha Kite Connect or yfinance without touching callers."""
    source = config.DATA_SOURCE.lower()
    if source == "alpha_vantage":
        return AlphaVantageFetcher()
    raise ValueError(
        f"Unknown DATA_SOURCE '{source}'. Only 'alpha_vantage' is implemented today — "
        "add a new DataFetcher subclass (e.g. ZerodhaFetcher) to support it."
    )

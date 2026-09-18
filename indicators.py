"""
Technical indicators, computed on daily OHLCV DataFrames
(columns: open, high, low, close, volume — ascending date index).

IMPORTANT CAVEAT ON VWAP: true VWAP is an intraday measure (cumulative
price*volume / cumulative volume within a single trading session). Alpha
Vantage's free tier only gives reliable daily bars, so `vwap_proxy` below
is a rolling N-day volume-weighted average price, not intraday VWAP. It's
useful as a volume-weighted "fair value" reference line, but don't treat
it as equivalent to session VWAP until you're on intraday data (Zerodha
or a paid Alpha Vantage plan).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


def typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3.0


def vwap_proxy(df: pd.DataFrame, window: int = config.VWAP_WINDOW) -> pd.Series:
    tp = typical_price(df)
    pv = tp * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum()


def rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's smoothing (standard RSI definition)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.fillna(100)  # avg_loss == 0 means pure uptrend -> RSI 100
    return rsi_series


def atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def volume_surge_ratio(df: pd.DataFrame, window: int = config.VOLUME_SURGE_LOOKBACK) -> pd.Series:
    """Today's volume divided by the trailing N-day average volume
    (excluding today, to avoid the average chasing itself upward)."""
    avg_vol = df["volume"].shift(1).rolling(window).mean()
    return df["volume"] / avg_vol


def breakout_flags(df: pd.DataFrame, lookback: int = config.BREAKOUT_LOOKBACK) -> pd.DataFrame:
    """Returns boolean columns: breakout_up (close > prior N-day high),
    breakout_down (close < prior N-day low)."""
    prior_high = df["high"].shift(1).rolling(lookback).max()
    prior_low = df["low"].shift(1).rolling(lookback).min()
    return pd.DataFrame({
        "breakout_up": df["close"] > prior_high,
        "breakout_down": df["close"] < prior_low,
        "prior_high": prior_high,
        "prior_low": prior_low,
    })


def relative_strength(symbol_returns: pd.Series, benchmark_returns: pd.Series,
                       lookback: int = config.RELATIVE_STRENGTH_LOOKBACK) -> float:
    """Cumulative return of the symbol over `lookback` trading days minus
    the cumulative return of the benchmark over the same window. Positive
    means the stock outperformed; negative means it lagged."""
    sym_cum = (1 + symbol_returns.tail(lookback)).prod() - 1
    bench_cum = (1 + benchmark_returns.tail(lookback)).prod() - 1
    return float(sym_cum - bench_cum)


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Attach every indicator as columns onto a copy of df."""
    out = df.copy()
    out["typical_price"] = typical_price(out)
    out["vwap_proxy"] = vwap_proxy(out)
    out["rsi"] = rsi(out)
    out["atr"] = atr(out)
    out["volume_surge_ratio"] = volume_surge_ratio(out)
    out["daily_return"] = out["close"].pct_change()

    bo = breakout_flags(out)
    out = out.join(bo)
    return out

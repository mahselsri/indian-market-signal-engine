"""
Signal Engine: orchestrates the pipeline stage between raw market data and
the (future) Groq AI analysis stage.

    universe symbols -> fetch OHLCV -> compute indicators -> score -> rank

Output is a list of Candidate objects, each carrying enough structured
detail (not just a score) that the next pipeline stage can hand it to an
LLM and ask "explain/validate this setup" without having to recompute
anything.
"""

from __future__ import annotations

import json
import os
import traceback
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

import pandas as pd

import config
import indicators
from data_fetcher import DataFetcher, get_fetcher
from symbols import get_universe


@dataclass
class Candidate:
    symbol: str
    as_of: str
    close: float
    pct_change_1d: float
    rsi: float
    atr: float
    atr_pct_of_price: float
    vwap_proxy: float
    price_vs_vwap_pct: float
    volume_surge_ratio: float
    breakout_up: bool
    breakout_down: bool
    prior_high: float
    prior_low: float
    relative_strength_20d: float
    score: float
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SignalEngine:
    def __init__(self, fetcher: Optional[DataFetcher] = None, universe_name: Optional[str] = None):
        self.fetcher = fetcher or get_fetcher()
        self.universe_name = universe_name or config.UNIVERSE
        self.universe = get_universe(self.universe_name)

    # ------------------------------------------------------------------
    # Data plumbing
    # ------------------------------------------------------------------
    def _get_benchmark_returns(self, per_symbol_returns: dict[str, pd.Series]) -> pd.Series:
        """Prefer an explicit BENCHMARK_SYMBOL if configured and fetchable;
        otherwise fall back to the equal-weighted average daily return of
        every symbol successfully scanned so far, which is a reasonable
        proxy for 'the market' when a clean index feed isn't available on
        the free tier."""
        if config.BENCHMARK_SYMBOL:
            try:
                bench_df = self.fetcher.get_daily_ohlcv(config.BENCHMARK_SYMBOL)
                return bench_df["close"].pct_change()
            except Exception as e:
                print(f"[warn] Could not fetch benchmark {config.BENCHMARK_SYMBOL}: {e}. "
                      "Falling back to universe-average benchmark.")

        if not per_symbol_returns:
            return pd.Series(dtype=float)
        aligned = pd.concat(per_symbol_returns.values(), axis=1)
        return aligned.mean(axis=1)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    @staticmethod
    def _score_row(row: pd.Series, rel_strength: float) -> tuple[float, list]:
        """Simple, transparent rule-based scoring (0-100). Every point
        added is logged as a human-readable reason so the Groq stage (or
        a human) can see exactly why a symbol was flagged, not just the
        final number."""
        score = 0.0
        reasons = []

        if row["breakout_up"]:
            score += 30
            reasons.append("Price broke above prior 20-day high")
        elif row["breakout_down"]:
            score -= 20
            reasons.append("Price broke below prior 20-day low")

        if pd.notna(row["volume_surge_ratio"]) and row["volume_surge_ratio"] >= config.VOLUME_SURGE_RATIO:
            score += 20
            reasons.append(f"Volume surge {row['volume_surge_ratio']:.2f}x the 20-day average")

        if pd.notna(row["rsi"]):
            if config.RSI_MIN <= row["rsi"] <= config.RSI_MAX:
                score += 15
                reasons.append(f"RSI {row['rsi']:.1f} in healthy trending range "
                                f"({config.RSI_MIN}-{config.RSI_MAX})")
            elif row["rsi"] > config.RSI_MAX:
                score -= 10
                reasons.append(f"RSI {row['rsi']:.1f} overbought")
            elif row["rsi"] < config.RSI_MIN:
                score -= 10
                reasons.append(f"RSI {row['rsi']:.1f} oversold/weak")

        if pd.notna(row["close"]) and pd.notna(row["vwap_proxy"]) and row["vwap_proxy"]:
            price_vs_vwap_pct = (row["close"] / row["vwap_proxy"] - 1) * 100
            if price_vs_vwap_pct > 0:
                score += 10
                reasons.append(f"Trading {price_vs_vwap_pct:.1f}% above its {config.VWAP_WINDOW}-day VWAP proxy")
            else:
                score -= 5
                reasons.append(f"Trading {abs(price_vs_vwap_pct):.1f}% below its {config.VWAP_WINDOW}-day VWAP proxy")

        if rel_strength > 0:
            bump = min(25.0, rel_strength * 100)  # cap contribution
            score += bump
            reasons.append(f"Outperforming benchmark by {rel_strength * 100:.1f}% over "
                            f"{config.RELATIVE_STRENGTH_LOOKBACK} days")
        else:
            score += max(-25.0, rel_strength * 100)
            reasons.append(f"Underperforming benchmark by {abs(rel_strength) * 100:.1f}% over "
                            f"{config.RELATIVE_STRENGTH_LOOKBACK} days")

        return score, reasons

    # ------------------------------------------------------------------
    # Main scan
    # ------------------------------------------------------------------
    def scan(self, top_n: Optional[int] = None) -> list[Candidate]:
        print(f"Scanning universe '{self.universe_name}' ({len(self.universe)} symbols)...")

        enriched: dict[str, pd.DataFrame] = {}
        returns_by_symbol: dict[str, pd.Series] = {}

        for i, symbol in enumerate(self.universe, start=1):
            try:
                raw = self.fetcher.get_daily_ohlcv(symbol)
                if len(raw) < max(config.RSI_PERIOD, config.ATR_PERIOD, config.BREAKOUT_LOOKBACK) + 5:
                    print(f"  [{i}/{len(self.universe)}] {symbol}: not enough history, skipping")
                    continue
                df = indicators.compute_all(raw)
                enriched[symbol] = df
                returns_by_symbol[symbol] = df["daily_return"]
                print(f"  [{i}/{len(self.universe)}] {symbol}: fetched & computed OK")
            except Exception as e:
                print(f"  [{i}/{len(self.universe)}] {symbol}: FAILED — {e}")
                continue

        benchmark_returns = self._get_benchmark_returns(returns_by_symbol)

        candidates: list[Candidate] = []
        for symbol, df in enriched.items():
            last = df.iloc[-1]
            if last[["rsi", "atr", "vwap_proxy", "volume_surge_ratio"]].isna().any():
                continue  # not enough warmed-up history for this row yet

            rel_strength = indicators.relative_strength(
                returns_by_symbol[symbol], benchmark_returns,
                lookback=config.RELATIVE_STRENGTH_LOOKBACK,
            )
            score, reasons = self._score_row(last, rel_strength)

            pct_change_1d = float(df["close"].pct_change().iloc[-1] * 100)
            price_vs_vwap_pct = float((last["close"] / last["vwap_proxy"] - 1) * 100) if last["vwap_proxy"] else 0.0

            candidates.append(Candidate(
                symbol=symbol,
                as_of=df.index[-1].strftime("%Y-%m-%d"),
                close=float(last["close"]),
                pct_change_1d=pct_change_1d,
                rsi=float(last["rsi"]),
                atr=float(last["atr"]),
                atr_pct_of_price=float(last["atr"] / last["close"] * 100),
                vwap_proxy=float(last["vwap_proxy"]),
                price_vs_vwap_pct=price_vs_vwap_pct,
                volume_surge_ratio=float(last["volume_surge_ratio"]),
                breakout_up=bool(last["breakout_up"]),
                breakout_down=bool(last["breakout_down"]),
                prior_high=float(last["prior_high"]),
                prior_low=float(last["prior_low"]),
                relative_strength_20d=rel_strength,
                score=round(score, 2),
                reasons=reasons,
            ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        if top_n:
            candidates = candidates[:top_n]
        return candidates

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    @staticmethod
    def save_candidates(candidates: list[Candidate], output_dir: Optional[str] = None) -> str:
        output_dir = output_dir or config.OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(output_dir, f"signals_{stamp}.json")
        with open(path, "w") as f:
            json.dump([c.to_dict() for c in candidates], f, indent=2)
        return path

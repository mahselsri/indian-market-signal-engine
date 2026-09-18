"""
CLI entry point.

Usage:
    python main.py
    python main.py --universe nifty50 --top 10
    python main.py --universe watchlist --top 5

Run from the repo root, with ALPHA_VANTAGE_API_KEY set in your environment
or a .env file.
"""

from __future__ import annotations

import argparse
import sys

from tabulate import tabulate

import config
from signal_engine import SignalEngine


def main():
    parser = argparse.ArgumentParser(description="Indian market signal engine scan")
    parser.add_argument("--universe", choices=["watchlist", "nifty50", "nifty100"],
                         default=config.UNIVERSE, help="Symbol universe to scan")
    parser.add_argument("--top", type=int, default=10, help="Number of top candidates to show/save")
    args = parser.parse_args()

    if not config.ALPHA_VANTAGE_API_KEY:
        print("ERROR: ALPHA_VANTAGE_API_KEY is not set. Create a .env file "
              "(see .env.example) or export it in your shell.", file=sys.stderr)
        sys.exit(1)

    engine = SignalEngine(universe_name=args.universe)
    candidates = engine.scan(top_n=args.top)

    if not candidates:
        print("\nNo candidates passed the indicator warm-up / filters this run.")
        return

    table_rows = [
        [
            c.symbol, c.as_of, round(c.close, 2), f"{c.pct_change_1d:+.2f}%",
            round(c.rsi, 1), f"{c.volume_surge_ratio:.2f}x",
            "UP" if c.breakout_up else ("DOWN" if c.breakout_down else "-"),
            f"{c.relative_strength_20d * 100:+.2f}%", c.score,
        ]
        for c in candidates
    ]
    headers = ["Symbol", "As of", "Close", "1D %", "RSI", "Vol Surge",
               "Breakout", "Rel Strength 20D", "Score"]
    print("\n" + tabulate(table_rows, headers=headers, tablefmt="github"))

    print("\nTop candidate reasoning:")
    for c in candidates[:3]:
        print(f"\n{c.symbol} (score {c.score}):")
        for r in c.reasons:
            print(f"  - {r}")

    saved_path = engine.save_candidates(candidates)
    print(f"\nSaved {len(candidates)} candidates to {saved_path}")
    print("(This JSON is the handoff point for the next stage — Groq AI analysis.)")


if __name__ == "__main__":
    main()

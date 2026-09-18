"""Not part of the shipped product — a quick offline smoke test using
synthetic OHLCV data, so the pipeline logic can be validated without
spending real Alpha Vantage API calls. Run with: python -m signal_engine.test_offline
"""
import numpy as np
import pandas as pd

from . import config
from .data_fetcher import DataFetcher
from .signal_engine import SignalEngine


class FakeFetcher(DataFetcher):
    def __init__(self, seed_map):
        self.seed_map = seed_map

    def get_daily_ohlcv(self, symbol: str) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed_map.get(symbol, 0))
        n = 260
        dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="B")
        drift = self.seed_map.get(symbol, 0) % 3 - 1  # -1, 0, or 1 -> down/flat/up bias
        returns = rng.normal(loc=0.0005 * drift, scale=0.015, size=n)
        close = 100 * np.cumprod(1 + returns)
        high = close * (1 + rng.uniform(0, 0.01, n))
        low = close * (1 - rng.uniform(0, 0.01, n))
        open_ = close * (1 + rng.uniform(-0.005, 0.005, n))
        volume = rng.uniform(1e5, 5e5, n)
        # inject a volume/breakout spike on the last bar for one symbol
        if self.seed_map.get(symbol) == 1:
            close[-1] = high[-30:-1].max() * 1.02
            high[-1] = close[-1] * 1.005
            volume[-1] = volume[:-1].mean() * 3
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )


def run():
    symbols = ["AAA.BSE", "BBB.BSE", "CCC.BSE", "DDD.BSE"]
    seed_map = {s: i for i, s in enumerate(symbols)}
    fetcher = FakeFetcher(seed_map)

    engine = SignalEngine(fetcher=fetcher, universe_name="watchlist")
    engine.universe = symbols  # override universe list directly for the test

    candidates = engine.scan(top_n=10)
    assert candidates, "Expected at least one candidate from synthetic data"

    for c in candidates:
        print(f"{c.symbol}: score={c.score}, rsi={c.rsi:.1f}, "
              f"breakout_up={c.breakout_up}, vol_surge={c.volume_surge_ratio:.2f}")
        for r in c.reasons:
            print(f"    - {r}")

    path = engine.save_candidates(candidates, output_dir="/tmp/signal_engine_test_output")
    print(f"\nSaved test output to {path}")
    print("\nOFFLINE SMOKE TEST PASSED")


if __name__ == "__main__":
    run()

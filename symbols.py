"""
Symbol universes.

Alpha Vantage's free tier reliably quotes Indian large-caps under the
".BSE" suffix (e.g. "RELIANCE.BSE"), not ".NS" (NSE) — so that's the
suffix used here. When you move to Zerodha/yfinance later, NSE trading
symbols (no suffix, or ".NS") are the norm instead — the fetcher layer
is where that translation should happen, not the signal engine.

NOTE: index constituents change over time (rebalanced twice a year).
Treat these lists as a reasonable starting point and refresh periodically
from an authoritative source (e.g. the NSE website) rather than trusting
them blindly for live trading decisions.
"""

# A small, safe-for-testing universe (10 liquid large-caps). Good default
# while you're validating logic against a 25-calls/day free API key.
WATCHLIST = [
    "RELIANCE.BSE",
    "TCS.BSE",
    "HDFCBANK.BSE",
    "INFY.BSE",
    "ICICIBANK.BSE",
    "HINDUNILVR.BSE",
    "ITC.BSE",
    "SBIN.BSE",
    "BHARTIARTL.BSE",
    "KOTAKBANK.BSE",
]

# NIFTY 50 constituents (BSE-suffixed for Alpha Vantage). Verify/update
# against the current NSE index sheet before relying on this for real
# scans — this list will drift out of date.
NIFTY50 = [
    "ADANIENT.BSE", "ADANIPORTS.BSE", "APOLLOHOSP.BSE", "ASIANPAINT.BSE",
    "AXISBANK.BSE", "BAJAJ-AUTO.BSE", "BAJFINANCE.BSE", "BAJAJFINSV.BSE",
    "BPCL.BSE", "BHARTIARTL.BSE", "BRITANNIA.BSE", "CIPLA.BSE",
    "COALINDIA.BSE", "DIVISLAB.BSE", "DRREDDY.BSE", "EICHERMOT.BSE",
    "GRASIM.BSE", "HCLTECH.BSE", "HDFCBANK.BSE", "HDFCLIFE.BSE",
    "HEROMOTOCO.BSE", "HINDALCO.BSE", "HINDUNILVR.BSE", "ICICIBANK.BSE",
    "ITC.BSE", "INDUSINDBK.BSE", "INFY.BSE", "JSWSTEEL.BSE",
    "KOTAKBANK.BSE", "LTIM.BSE", "LT.BSE", "M&M.BSE",
    "MARUTI.BSE", "NTPC.BSE", "NESTLEIND.BSE", "ONGC.BSE",
    "POWERGRID.BSE", "RELIANCE.BSE", "SBILIFE.BSE", "SHRIRAMFIN.BSE",
    "SBIN.BSE", "SUNPHARMA.BSE", "TCS.BSE", "TATACONSUM.BSE",
    "TATAMOTORS.BSE", "TATASTEEL.BSE", "TECHM.BSE", "TITAN.BSE",
    "ULTRACEMCO.BSE", "WIPRO.BSE",
]

# NIFTY 100 = NIFTY 50 + next 50 (Nifty Next 50). Trimmed here to a
# representative extra set — extend as needed.
NIFTY_NEXT_50_SAMPLE = [
    "ABB.BSE", "ADANIENSOL.BSE", "ADANIGREEN.BSE", "ADANIPOWER.BSE",
    "AMBUJACEM.BSE", "BANKBARODA.BSE", "BERGEPAINT.BSE", "BOSCHLTD.BSE",
    "CANBK.BSE", "CGPOWER.BSE", "CHOLAFIN.BSE", "COLPAL.BSE",
    "DABUR.BSE", "DLF.BSE", "GAIL.BSE", "GODREJCP.BSE",
    "HAVELLS.BSE", "ICICIGI.BSE", "ICICIPRULI.BSE", "IOC.BSE",
    "IRFC.BSE", "JINDALSTEL.BSE", "LICI.BSE", "LODHA.BSE",
    "MARICO.BSE", "MOTHERSON.BSE", "NAUKRI.BSE", "PIDILITIND.BSE",
    "PFC.BSE", "PNB.BSE", "RECLTD.BSE", "SIEMENS.BSE",
    "TATAPOWER.BSE", "TORNTPHARM.BSE", "TVSMOTOR.BSE", "UNITDSPR.BSE",
    "VBL.BSE", "VEDL.BSE", "ZOMATO.BSE", "ZYDUSLIFE.BSE",
]

NIFTY100 = NIFTY50 + NIFTY_NEXT_50_SAMPLE


def get_universe(name: str) -> list:
    name = (name or "").strip().lower()
    if name == "nifty50":
        return NIFTY50
    if name == "nifty100":
        return NIFTY100
    if name == "watchlist":
        return WATCHLIST
    raise ValueError(f"Unknown universe '{name}'. Use nifty50, nifty100, or watchlist.")

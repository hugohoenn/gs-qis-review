"""Pull public daily prices for GS QIS funds, replication peers, and a liquid ETF factor basket."""
import pandas as pd, yfinance as yf
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; RAW = ROOT / "data" / "raw"; OUT = ROOT / "output"; FIG = OUT / "figures"

FUNDS = {"GJRTX": "GS Absolute Return Tracker (Inst.)", "GARTX": "GS Absolute Return Tracker (A)"}
PEERS = {"QAI": "IQ Hedge Multi-Strategy Tracker ETF", "HDG": "ProShares Hedge Replication ETF"}
# Liquid, investable building blocks a replicator could actually hold
BASKET = {"SPY": "US equity", "IWM": "US small cap", "EFA": "Developed ex-US equity", "EEM": "Emerging equity",
          "IEF": "US Treasuries 7-10y", "LQD": "IG credit", "HYG": "High yield", "DBC": "Commodities",
          "GLD": "Gold", "UUP": "US dollar", "BIL": "T-bills (cash)"}
BENCH = {"AGG": "US aggregate bonds"}

def pull(start="2008-01-01"):
    tick = list(FUNDS) + list(PEERS) + list(BASKET) + list(BENCH)
    px = yf.download(tick, start=start, progress=False, auto_adjust=True)["Close"]
    px = px.dropna(how="all")
    px.to_parquet(RAW / "prices.parquet")
    return px

if __name__ == "__main__":
    px = pull()
    print(px.shape, px.index[0].date(), "->", px.index[-1].date())
    print(px.notna().idxmax().sort_values().to_string())

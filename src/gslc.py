"""Replicate the Goldman Sachs ActiveBeta U.S. Large Cap Equity Index (GSLC) from its published rulebook
(Solactive/GSAM methodology, 2 April 2024) using free data, then compare to the ETF's actual returns.

Published and implemented:            Not published (fitted on 2015-20, tested 2021-26):
  - value: B/P, S/P, FCF/P (E/P financials)   - Cut-off Score
  - momentum: beta- & vol-adjusted 11m return  - Maximum Stock Underweight
  - quality: gross profit/assets, ROE fallback  Not implemented (disclosed): turnover-minimisation
  - low vol: 1/std(12m daily)                   technique, beta bands, 2bp minimum weight
  - rank -> score in [-1,+1]; over/underweight mechanics; sector bands (full neutrality here)
  - equal-weight the 4 subindexes; quarterly rebalance
Universe proxy: current S&P 500 constituents (Solactive US Large Cap is ~the 500 largest US stocks).
Fundamentals: SEC EDGAR, point-in-time by filing date. Free cash flow proxied by operating cash flow.
"""
import sys, itertools, numpy as np, pandas as pd, yfinance as yf
sys.path.insert(0, "/home/claude/factor-strategy/src")
from data import RAW, OUT, FIG
import config as fcfg
from factors import load_panels, month_ends, asof_panel
from portfolio import sector_rescale

REBAL_MONTHS = [1, 4, 7, 10]         # selection at these month-ends; index rebalances first Wed of Feb/May/Aug/Nov
START, SPLIT = "2015-10-31", "2020-12-31"

def build_inputs():
    adj, close, uni, long = load_panels()
    tickers = adj.columns; mends = month_ends(adj)
    padj = adj.resample("ME").last(); dret = adj.pct_change(fill_method=None)
    F = {c: asof_panel(long, c, mends, tickers) for c in ["equity", "assets", "netinc", "ocf", "revenue", "gross"]}
    mktcap = pd.read_parquet(fcfg.PROC / "mktcap.parquet"); invest = pd.read_parquet(fcfg.PROC / "invest.parquet")
    beta = pd.read_parquet(fcfg.PROC / "beta.parquet")
    sectors = uni["sector"].reindex(tickers); fin = sectors.eq("Financials")
    vol = dret.rolling(252, min_periods=200).std().resample("ME").last()
    # market (cap-weighted universe) 11m return for beta adjustment
    w = mktcap.div(mktcap.sum(axis=1), axis=0)
    mret = (w.shift(1) * padj.pct_change(fill_method=None)).sum(axis=1)
    mkt11 = (1 + mret).rolling(11).apply(np.prod, raw=True).shift(1) - 1
    ret11 = padj.shift(1) / padj.shift(12) - 1
    mom = (ret11.sub(beta.mul(mkt11, axis=0))).div(vol * np.sqrt(252))        # beta- and vol-adjusted
    bp = F["equity"] / mktcap; sp = F["revenue"] / mktcap; cfp = F["ocf"] / mktcap; ep = F["netinc"] / mktcap
    gpa = F["gross"] / F["assets"]; roe = F["netinc"] / F["equity"]
    return dict(padj=padj, mktcap=mktcap, invest=invest, sectors=sectors, fin=fin, vol=vol, mom=mom,
                bp=bp, sp=sp, cfp=cfp, ep=ep, gpa=gpa, roe=roe, mends=mends)

def pct_rank(s):                       # 0..1 percentile among non-missing
    return s.rank(pct=True)

def score(s):                          # rulebook: ranks -> fractional scores in [-1, +1]
    r = s.rank(); n = r.max()
    return 2 * (r - 1) / (n - 1) - 1

def factor_scores(I, t):
    inv = I["invest"].loc[t]; fin = I["fin"]
    v3 = I["cfp"].loc[t].where(~fin, I["ep"].loc[t])
    value = pd.concat([pct_rank(I["bp"].loc[t].where(inv)), pct_rank(I["sp"].loc[t].where(inv)), pct_rank(v3.where(inv))], axis=1).mean(axis=1)
    q = I["gpa"].loc[t].where(~fin & I["gpa"].loc[t].notna(), np.nan)
    qual = pd.concat([pct_rank(q.where(inv)), pct_rank(I["roe"].loc[t].where(inv & q.isna()))], axis=1).max(axis=1)
    lowvol = (1 / I["vol"].loc[t]).where(inv)
    mom = I["mom"].loc[t].where(inv)
    return {"value": score(value.where(inv)), "momentum": score(mom), "quality": score(qual), "lowvol": score(lowvol)}

def subindex(sc, iuw, cutoff, max_under, cap_mult, sectors, sector_neutral):
    """Rulebook section 1.2: rescale around cut-off, underweight down to zero, redistribute to overweights, cap."""
    s = sc.reindex(iuw.index); ok = iuw.gt(0) & s.notna()
    iuw = iuw.where(ok, 0.0); s = s.where(ok, 0.0)
    r = pd.Series(0.0, index=s.index)
    lo = s <= cutoff; hi = s > cutoff
    r[lo] = (s[lo] - cutoff) / (cutoff + 1) if cutoff > -1 else 0       # -> [-1, 0]
    r[hi] = (s[hi] - cutoff) / (1 - cutoff)                                # -> (0, 1]
    tgt = iuw.copy()
    tgt[lo] = np.maximum(iuw[lo] + r[lo] * max_under, 0.0)
    total_under = (iuw[lo] - tgt[lo]).sum()
    tgt[hi] = iuw[hi] + r[hi] / r[hi].sum() * total_under
    tgt = np.minimum(tgt, cap_mult * iuw)                                 # cap based on universe weight
    tgt = tgt / tgt.sum()
    if sector_neutral: tgt = sector_rescale(tgt, iuw, sectors)
    return tgt

def replicate(I, cutoff, max_under, cap_mult, start=START, end=None):
    padj = I["padj"]; mret = padj.pct_change(fill_method=None)
    dates = [d for d in I["mends"] if d >= pd.Timestamp(start) and (end is None or d <= pd.Timestamp(end))]
    rets, w = {}, None
    for t in dates:
        if t.month in REBAL_MONTHS or w is None:
            inv = I["invest"].loc[t]; iuw = I["mktcap"].loc[t].where(inv).fillna(0.0); iuw = iuw / iuw.sum()
            sc = factor_scores(I, t)
            subs = [subindex(sc[f], iuw, cutoff, max_under, cap_mult, I["sectors"], sector_neutral=(f != "momentum")) for f in sc]
            w = sum(subs) / 4
        nxt_i = mret.index.get_loc(t) + 1
        if nxt_i >= len(mret.index): break
        nxt = mret.index[nxt_i]; r = mret.loc[nxt].reindex(w.index).fillna(0.0)
        rets[nxt] = float((w * r).sum())
        g = w * (1 + r); w = g / g.sum()
    return pd.Series(rets)

def etf_monthly(tickers, start="2015-01-01"):
    px = yf.download(tickers, start=start, progress=False, auto_adjust=True)["Close"]
    px.to_parquet(RAW / "gslc_peers.parquet")
    return px.resample("ME").last().pct_change(fill_method=None)

if __name__ == "__main__":
    I = build_inputs()
    etf = etf_monthly(["GSLC", "SPY", "LRGF", "QUAL", "MTUM", "VLUE", "USMV", "JQUA", "DFAC", "IVV"])
    gslc = etf["GSLC"].dropna()
    # ---- calibrate the two unpublished parameters on 2015-2020 ----
    grid = list(itertools.product([-0.25, 0.0, 0.25], [0.0025, 0.005, 0.01], [2.0, 3.0, 5.0]))
    res = []
    for c, m, k in grid:
        rep = replicate(I, c, m, k, end=SPLIT)
        a = pd.concat([rep, gslc], axis=1, keys=["rep", "gslc"]).dropna()
        a = a.loc[:SPLIT]
        te = (a.rep - a.gslc).std() * 12 ** .5
        res.append({"cutoff": c, "max_under": m, "cap": k, "te_insample": te, "corr": a.rep.corr(a.gslc)})
    res = pd.DataFrame(res).sort_values("te_insample"); res.to_csv(OUT / "gslc_calibration.csv", index=False)
    best = res.iloc[0]; print("calibration (in-sample 2015-20):\n", res.head(5).round(4).to_string(index=False))
    # ---- full run with fitted parameters ----
    rep = replicate(I, best.cutoff, best.max_under, best["cap"])
    df = pd.concat([rep, gslc, etf["SPY"]], axis=1, keys=["replica", "gslc", "spy"]).dropna()
    df.to_parquet(OUT / "gslc_replica.parquet")
    def stats(d):
        te = (d.replica - d.gslc).std() * 12 ** .5; te_spy = (d.gslc - d.spy).std() * 12 ** .5
        ann = lambda s: (1 + s).prod() ** (12 / len(s)) - 1
        return {"TE replica vs GSLC": te, "Corr replica-GSLC": d.replica.corr(d.gslc), "Ann replica": ann(d.replica), "Ann GSLC": ann(d.gslc),
                "Ann SPY": ann(d.spy), "GSLC TE vs SPY": te_spy, "GSLC active vs SPY": ann(d.gslc) - ann(d.spy),
                "Replica active vs SPY": ann(d.replica) - ann(d.spy), "Corr active returns (rep vs GSLC, both vs SPY)": (d.replica - d.spy).corr(d.gslc - d.spy)}
    out = pd.DataFrame({"In-sample 2015-20": stats(df.loc[:SPLIT]), "Out-of-sample 2021-26": stats(df.loc["2021":]), "Full": stats(df)})
    out.to_csv(OUT / "gslc_fit.csv"); pd.set_option("display.float_format", lambda x: f"{x:.3f}"); print("\n", out.to_string())
    cal = (1 + df).groupby(df.index.year).prod() - 1; cal["gslc_active"] = cal.gslc - cal.spy; cal["replica_active"] = cal.replica - cal.spy
    cal.to_csv(OUT / "gslc_calendar.csv"); print("\n", cal.round(3).to_string())

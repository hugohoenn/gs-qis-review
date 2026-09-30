"""Reverse-engineer the GS Absolute Return Tracker Fund (GJRTX) from public prices.

1. Static OLS of monthly excess returns on a liquid ETF basket (what does it hold on average?)
2. Rolling 24-month OLS and a random-walk Kalman filter (how have exposures moved?)
3. Out-of-sample ETF clone: betas estimated through month t, applied to month t+1
   (how replicable is the fund with instruments anyone can buy?)
4. Fama-French 5 + momentum style regression
5. Peer comparison: QAI, HDG, 60/40, cash
"""
import io, zipfile, requests, numpy as np, pandas as pd, statsmodels.api as sm
from data import RAW, OUT, FIG, BASKET, FUNDS, PEERS

FUND = "GJRTX"                     # institutional share class: fewer fee distortions than the A class
X_COLS = ["SPY", "IWM", "EFA", "EEM", "IEF", "LQD", "HYG", "DBC", "GLD", "UUP"]
ROLL = 24

def monthly():
    px = pd.read_parquet(RAW / "prices.parquet")
    m = px.resample("ME").last().pct_change(fill_method=None).dropna(how="all")
    m = m.loc["2008-07":]                      # first full month for GARTX
    rf = m["BIL"].fillna(0)
    ex = m.sub(rf, axis=0)
    return m, ex, rf

def static_ols(y, X):
    Xc = sm.add_constant(X); mod = sm.OLS(y, Xc, missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    out = pd.DataFrame({"beta": mod.params, "t": mod.tvalues}); out.loc["const", "beta"] *= 12
    return out.rename(index={"const": "Alpha (ann.)"}), mod.rsquared, mod.resid

def rolling_ols(y, X, window=ROLL):
    betas = {}
    for i in range(window, len(y) + 1):
        yy, XX = y.iloc[i - window:i], X.iloc[i - window:i]
        b = np.linalg.lstsq(sm.add_constant(XX).values, yy.values, rcond=None)[0]
        betas[y.index[i - 1]] = dict(zip(["alpha"] + list(X.columns), b))
    return pd.DataFrame(betas).T

def kalman(y, X, q_grid=(1e-6, 3e-6, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3)):
    """Time-varying regression: beta_t = beta_{t-1} + w_t (var q), y_t = x_t' beta_t + v_t (var r).
    r from static OLS residuals; q picked by one-step-ahead log-likelihood. Returns filtered betas."""
    Xc = sm.add_constant(X).values; yv = y.values; n, k = Xc.shape
    b0 = np.linalg.lstsq(Xc, yv, rcond=None)[0]; r = np.var(yv - Xc @ b0)
    best = None
    for q in q_grid:
        b, P = b0.copy(), np.eye(k) * 1e-2; ll = 0.0; path = []
        for t in range(n):
            P = P + np.eye(k) * q
            x = Xc[t]; f = x @ P @ x + r; e = yv[t] - x @ b
            ll += -0.5 * (np.log(2 * np.pi * f) + e ** 2 / f)
            K = P @ x / f; b = b + K * e; P = P - np.outer(K, x @ P)
            path.append(b.copy())
        if best is None or ll > best[0]: best = (ll, q, np.array(path))
    ll, q, path = best
    return pd.DataFrame(path, index=y.index, columns=["alpha"] + list(X.columns)), q

def oos_clone(y, X, rf, window=ROLL):
    """Betas estimated on months [t-window, t] applied to month t+1. No alpha term (cannot be bought)."""
    rows = {}
    for i in range(window, len(y) - 1):
        yy, XX = y.iloc[i - window:i], X.iloc[i - window:i]
        b = np.linalg.lstsq(sm.add_constant(XX).values, yy.values, rcond=None)[0][1:]
        nxt = y.index[i]
        rows[nxt] = {"clone_ex": float(X.loc[nxt].values @ b), "fund_ex": y.loc[nxt], "gross": b.sum(), "long": b[b > 0].sum()}
    df = pd.DataFrame(rows).T
    df["clone"] = df["clone_ex"] + rf.reindex(df.index); df["fund"] = df["fund_ex"] + rf.reindex(df.index)
    return df

def ff_factors():
    def _get(url):
        z = zipfile.ZipFile(io.BytesIO(requests.get(url, timeout=60).content)); txt = z.read(z.namelist()[0]).decode("latin1").splitlines()
        s = next(i for i, l in enumerate(txt) if l.strip()[:6].isdigit() and len(l.strip()[:6]) == 6)
        rows = []
        for l in txt[s:]:
            p = [x.strip() for x in l.split(",")]
            if len(p[0]) != 6 or not p[0].isdigit(): break
            rows.append(p)
        df = pd.DataFrame(rows).set_index(0).astype(float) / 100
        df.columns = [h.strip() for h in txt[s - 1].split(",")[1:]][:df.shape[1]]
        df.index = pd.to_datetime(df.index, format="%Y%m") + pd.offsets.MonthEnd(0); return df
    ff = _get("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip")
    mom = _get("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"); mom.columns = ["MOM"]
    return ff.join(mom, how="inner")

def metrics(r, rf, mkt):
    r = r.dropna(); rf = rf.reindex(r.index); mkt = mkt.reindex(r.index)
    n = len(r); ann = (1 + r).prod() ** (12 / n) - 1; ex = r - rf
    cum = (1 + r).cumprod(); dd = cum / cum.cummax() - 1
    return pd.Series({"Ann. return": ann, "Volatility": r.std() * 12 ** .5, "Sharpe": ex.mean() / ex.std() * 12 ** .5,
                      "Max drawdown": dd.min(), "Beta to SPY": np.cov(r, mkt)[0, 1] / mkt.var(), "Corr. to SPY": r.corr(mkt),
                      "Start": r.index[0].strftime("%Y-%m")})

if __name__ == "__main__":
    m, ex, rf = monthly()
    y = ex[FUND].dropna(); X = ex.loc[y.index, X_COLS]

    stat, r2, resid = static_ols(y, X)
    print(f"=== Static OLS, {y.index[0]:%b %Y}-{y.index[-1]:%b %Y}, R2 = {r2:.2f}\n", stat.round(3).to_string())
    roll = rolling_ols(y, X); kf, q = kalman(y, X)
    print(f"\nKalman q = {q:g}")
    clone = oos_clone(y, X, rf)
    te = (clone.fund - clone.clone).std() * 12 ** .5; corr = clone.fund.corr(clone.clone)
    ann = lambda s: (1 + s).prod() ** (12 / len(s)) - 1
    print(f"\n=== OOS ETF clone ({clone.index[0]:%b %Y}-): TE {te:.2%}, corr {corr:.2f}, fund {ann(clone.fund):.2%} vs clone {ann(clone.clone):.2%}/yr, "
          f"avg gross exposure {clone.gross.mean():.2f}")

    ff = ff_factors().reindex(y.index)
    ffreg = sm.OLS(y, sm.add_constant(ff[["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]]), missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    ffo = pd.DataFrame({"beta": ffreg.params, "t": ffreg.tvalues}); ffo.loc["const", "beta"] *= 12; ffo = ffo.rename(index={"const": "Alpha (ann.)"})
    print(f"\n=== FF5+MOM, R2 = {ffreg.rsquared:.2f}\n", ffo.round(3).to_string())

    sixty = 0.6 * m["SPY"] + 0.4 * m["AGG"]
    comp = {"GARTX (Inst.)": m[FUND], "GARTX (A)": m["GARTX"], "QAI": m["QAI"], "HDG": m["HDG"], "60/40 SPY/AGG": sixty,
            "ETF clone (OOS)": clone.clone, "T-bills": m["BIL"]}
    common = m["HDG"].dropna().index          # common window since Jul 2011 for fair comparison
    peer_full = pd.DataFrame({k: metrics(v, rf, m["SPY"]) for k, v in comp.items()}).T
    peer_common = pd.DataFrame({k: metrics(v.reindex(common), rf, m["SPY"]) for k, v in comp.items()}).T
    print("\n=== Peers, common window", common[0].strftime("%b %Y"), "\n", peer_common.to_string())

    stress = {"GFC (Jul 2008-Feb 2009)": ("2008-07", "2009-02"), "2011 (Aug-Sep)": ("2011-08", "2011-09"), "Q4 2018": ("2018-10", "2018-12"),
              "COVID (Feb-Mar 2020)": ("2020-02", "2020-03"), "2022": ("2022-01", "2022-12")}
    series = {"GARTX": m[FUND], "SPY": m["SPY"], "60/40": sixty, "QAI": m["QAI"]}
    st = pd.DataFrame({k: {n: (1 + v.loc[s:e]).prod() - 1 for n, (s, e) in stress.items()} for k, v in series.items()})
    print("\n=== Stress\n", st.round(3).to_string())

    for n, o in [("static_ols", stat), ("rolling_betas", roll), ("kalman_betas", kf), ("clone", clone), ("ff_regression", ffo),
                 ("peers_common", peer_common), ("peers_full", peer_full), ("stress", st)]:
        o.to_csv(OUT / f"gartx_{n}.csv")
    pd.Series({"static_r2": r2, "ff_r2": ffreg.rsquared, "clone_te": te, "clone_corr": corr, "kalman_q": q}).to_csv(OUT / "gartx_summary.csv")

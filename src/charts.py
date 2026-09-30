import pandas as pd, numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from data import OUT, FIG, RAW
from gartx import monthly, FUND, X_COLS
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
NAVY, GREY = "#0B3D91", "#9AA5B1"
m, ex, rf = monthly()
kf = pd.read_csv(OUT / "gartx_kalman_betas.csv", index_col=0, parse_dates=True)
roll = pd.read_csv(OUT / "gartx_rolling_betas.csv", index_col=0, parse_dates=True)
clone = pd.read_csv(OUT / "gartx_clone.csv", index_col=0, parse_dates=True)
cum = lambda s: (1 + s.dropna()).cumprod()

# 1. Kalman exposures, grouped
groups = {"Equity (SPY+IWM+EFA+EEM)": ["SPY", "IWM", "EFA", "EEM"], "Credit (LQD+HYG)": ["LQD", "HYG"], "Treasuries (IEF)": ["IEF"],
          "Commodities & gold": ["DBC", "GLD"], "US dollar": ["UUP"]}
g = pd.DataFrame({k: kf[v].sum(axis=1) for k, v in groups.items()}).loc["2009":]
fig, ax = plt.subplots(figsize=(9, 4.4))
g.plot(ax=ax, lw=1.8, color=[NAVY, "#2A9D8F", "#E9C46A", "#B23A48", GREY]); ax.axhline(0, color="k", lw=.6)
ax.set_title("GARTX inferred exposures (Kalman filter, monthly, net-of-cash betas to liquid ETFs)"); ax.legend(frameon=False, ncol=3, fontsize=8.5); ax.set_xlabel("")
fig.tight_layout(); fig.savefig(FIG / "gartx_exposures.png", dpi=180); plt.close(fig)

# 2. fund vs OOS clone vs peers vs 60/40, common window
start = m["HDG"].dropna().index[0]
sixty = 0.6 * m["SPY"] + 0.4 * m["AGG"]
fig, ax = plt.subplots(figsize=(9, 4.4))
for name, s, c, lw in [("GARTX (Inst.)", m[FUND], NAVY, 2.2), ("OOS ETF clone", clone["clone"], "#2A9D8F", 1.8), ("QAI", m["QAI"], "#E9C46A", 1.4),
                       ("HDG", m["HDG"], "#B23A48", 1.4), ("60/40 SPY/AGG", sixty, GREY, 1.6), ("T-bills", m["BIL"], "#333", 1.0)]:
    cum(s.loc[start:]).plot(ax=ax, label=name, color=c, lw=lw)
ax.set_title(f"Growth of $1 since {start:%b %Y}: GARTX vs. its ETF clone, replication peers and 60/40"); ax.legend(frameon=False, ncol=3, fontsize=8.5); ax.set_xlabel("")
fig.tight_layout(); fig.savefig(FIG / "gartx_vs_peers.png", dpi=180); plt.close(fig)

# 3. fund vs clone full window + tracking difference
fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
cum(clone["fund"]).plot(ax=a1, color=NAVY, lw=2, label="GARTX (Inst.)"); cum(clone["clone"]).plot(ax=a1, color="#2A9D8F", lw=2, label="OOS ETF clone (24m rolling betas, no alpha)")
a1.set_title("Fund vs. out-of-sample ETF clone"); a1.legend(frameon=False); a1.set_xlabel("")
diff = (cum(clone["fund"]) / cum(clone["clone"]) - 1) * 100
a2.plot(diff.index, diff, color="#B23A48", lw=1.6); a2.axhline(0, color="k", lw=.6); a2.set_title("Cumulative fund minus clone (%)"); a2.set_xlabel("")
fig.tight_layout(); fig.savefig(FIG / "gartx_clone.png", dpi=180); plt.close(fig)

# 4. rolling beta and correlation to SPY
fig, ax = plt.subplots(figsize=(9, 3.6))
b = m[FUND].rolling(24).cov(m["SPY"]) / m["SPY"].rolling(24).var(); c = m[FUND].rolling(24).corr(m["SPY"])
b.plot(ax=ax, color=NAVY, lw=2, label="Beta to SPY (24m)"); c.plot(ax=ax, color=GREY, lw=1.6, label="Correlation to SPY (24m)")
ax.axhline(0, color="k", lw=.6); ax.set_title("GARTX: rolling beta and correlation to US equities"); ax.legend(frameon=False); ax.set_xlabel("")
fig.tight_layout(); fig.savefig(FIG / "gartx_beta.png", dpi=180); plt.close(fig)

# 5. drawdowns
fig, ax = plt.subplots(figsize=(9, 3.4))
for name, s, c in [("GARTX", m[FUND], NAVY), ("SPY", m["SPY"], GREY), ("60/40", sixty, "#E9C46A")]:
    cs = cum(s); (cs / cs.cummax() - 1).plot(ax=ax, color=c, lw=1.6, label=name)
ax.set_title("Drawdowns since Jul 2008"); ax.legend(frameon=False); ax.set_xlabel("")
fig.tight_layout(); fig.savefig(FIG / "gartx_drawdown.png", dpi=180); plt.close(fig)
print("charts done"); print("avg Kalman group exposures (2015+):"); print(g.loc["2015":].mean().round(3).to_string())

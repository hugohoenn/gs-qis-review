import sys, numpy as np, pandas as pd, statsmodels.api as sm, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, "/home/claude/factor-strategy/src")
from data import RAW, OUT, FIG
import config as fcfg
from gartx import ff_factors, metrics
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
NAVY, GREY = "#0B3D91", "#9AA5B1"
SPLIT = "2020-12-31"

df = pd.read_parquet(OUT / "gslc_replica.parquet")
# same-universe cap-weighted benchmark for the replica (removes survivorship from the active comparison)
mk = pd.read_parquet(fcfg.PROC / "mktcap.parquet"); inv = pd.read_parquet(fcfg.PROC / "invest.parquet"); padj = pd.read_parquet(fcfg.PROC / "padj.parquet")
w = mk.where(inv).fillna(0); w = w.div(w.sum(axis=1), axis=0); mret = padj.pct_change(fill_method=None)
bench = (w.shift(1) * mret.fillna(0)).sum(axis=1).reindex(df.index)
df["bench"] = bench; df["rep_active"] = df.replica - df.bench; df["gslc_active"] = df.gslc - df.spy

def block(d):
    ann = lambda s: (1 + s).prod() ** (12 / len(s)) - 1
    return {"GSLC active vs SPY (ann.)": ann(d.gslc) - ann(d.spy), "Replica active vs own universe (ann.)": ann(d.replica) - ann(d.bench),
            "GSLC TE vs SPY": d.gslc_active.std() * 12 ** .5, "Replica TE vs universe": d.rep_active.std() * 12 ** .5,
            "Corr of active returns": d.rep_active.corr(d.gslc_active),
            "Sign agreement (months)": (np.sign(d.rep_active) == np.sign(d.gslc_active)).mean()}
fit = pd.DataFrame({"In-sample 2015-20": block(df.loc[:SPLIT]), "Out-of-sample 2021-26": block(df.loc["2021":]), "Full": block(df)})
fit.to_csv(OUT / "gslc_active_fit.csv"); pd.set_option("display.float_format", lambda x: f"{x:.3f}"); print(fit.to_string())

# --- what explains GSLC's active returns? (a) FF5+MOM  (b) my four single-factor sleeves' active returns
ff = ff_factors().reindex(df.index)
m1 = sm.OLS(df.gslc_active, sm.add_constant(ff[["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]]), missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": 3})
ffo = pd.DataFrame({"coef": m1.params, "t": m1.tvalues}); ffo.loc["const", "coef"] *= 12; ffo = ffo.rename(index={"const": "Alpha (ann.)"})
sleeves = pd.DataFrame({f: (lambda r: r.net - r.bench)(pd.read_parquet(fcfg.OUT / f"returns_{f}.parquet")) for f in ["value", "momentum", "quality", "lowvol"]}).reindex(df.index)
m2 = sm.OLS(df.gslc_active, sm.add_constant(sleeves), missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": 3})
slo = pd.DataFrame({"coef": m2.params, "t": m2.tvalues}); slo.loc["const", "coef"] *= 12; slo = slo.rename(index={"const": "Alpha (ann.)"})
print(f"\nFF5+MOM on GSLC active, R2 {m1.rsquared:.2f}\n", ffo.round(3).to_string()); print(f"\nSleeves on GSLC active, R2 {m2.rsquared:.2f}\n", slo.round(3).to_string())
ffo.to_csv(OUT / "gslc_ff.csv"); slo.to_csv(OUT / "gslc_sleeves.csv"); pd.Series({"ff_r2": m1.rsquared, "sleeve_r2": m2.rsquared}).to_csv(OUT / "gslc_r2.csv")

# --- peers (common window = DFAC start Jun 2021 is too short; use JQUA start Dec 2017 and drop DFAC; DFAC separately)
px = pd.read_parquet(RAW / "gslc_peers.parquet"); em = px.resample("ME").last().pct_change(fill_method=None)
rf = ff["RF"].reindex(em.index).ffill().fillna(0)
fees = {"GSLC": 0.09, "IVV": 0.03, "LRGF": 0.08, "QUAL": 0.15, "MTUM": 0.15, "VLUE": 0.15, "USMV": 0.15, "JQUA": 0.12, "DFAC": 0.17}
start = em["JQUA"].dropna().index[0]
rows = {}
for t in ["GSLC", "IVV", "LRGF", "QUAL", "MTUM", "VLUE", "USMV", "JQUA"]:
    r = em[t].loc[start:]; b = em["SPY"].loc[start:]; act = r - b; ann = lambda s: (1 + s).prod() ** (12 / len(s)) - 1
    rows[t] = {"Expense ratio %": fees[t], "Ann. return": ann(r), "Active vs SPY": ann(r) - ann(b), "Tracking error": act.std() * 12 ** .5,
               "Info ratio": act.mean() / act.std() * 12 ** .5, "Sharpe": (r - rf.loc[start:]).mean() / r.std() * 12 ** .5,
               "Max DD": ((1 + r).cumprod() / (1 + r).cumprod().cummax() - 1).min(), "Beta": np.cov(r, b)[0, 1] / b.var()}
peers = pd.DataFrame(rows).T; peers.to_csv(OUT / "gslc_peers.csv"); print(f"\nPeers since {start:%b %Y}\n", peers.round(3).to_string())

# --- charts
cal = pd.read_csv(OUT / "gslc_calendar.csv", index_col=0)
fig, ax = plt.subplots(figsize=(9, 3.8)); x = np.arange(len(cal)); ax.bar(x - .2, cal.gslc_active * 100, .4, color=NAVY, label="GSLC minus SPY")
rep_act_cal = (1 + df.rep_active).groupby(df.index.year).prod() - 1
ax.bar(x + .2, rep_act_cal.reindex(cal.index).values * 100, .4, color=GREY, label="Rulebook replica minus own universe")
ax.set_xticks(x); ax.set_xticklabels(cal.index.astype(str)); ax.axhline(0, color="k", lw=.6); ax.set_ylabel("%"); ax.set_title("Calendar-year active returns"); ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(FIG / "gslc_calendar_active.png", dpi=180); plt.close(fig)

fig, ax = plt.subplots(figsize=(9, 4.2))
((1 + df.gslc).cumprod() / (1 + df.spy).cumprod()).plot(ax=ax, color=NAVY, lw=2.2, label="GSLC / SPY")
((1 + df.replica).cumprod() / (1 + df.bench).cumprod()).plot(ax=ax, color=GREY, lw=1.8, label="Replica / own cap-weighted universe")
ax.axvline(pd.Timestamp(SPLIT), color="k", lw=.8, ls="--"); ax.text(pd.Timestamp(SPLIT), ax.get_ylim()[1], "  calibration | test", va="top", fontsize=8.5)
ax.axhline(1, color="k", lw=.6); ax.set_title("Relative wealth vs. cap-weighted benchmark since GSLC launch"); ax.legend(frameon=False); ax.set_xlabel("")
fig.tight_layout(); fig.savefig(FIG / "gslc_relative.png", dpi=180); plt.close(fig)

fig, ax = plt.subplots(figsize=(9, 3.6))
ax.scatter(df.rep_active * 100, df.gslc_active * 100, s=14, color=NAVY, alpha=.7); ax.axhline(0, color="k", lw=.5); ax.axvline(0, color="k", lw=.5)
ax.set_xlabel("Replica active return, % (monthly)"); ax.set_ylabel("GSLC active return, %"); ax.set_title(f"Monthly active returns: replica vs GSLC (corr {df.rep_active.corr(df.gslc_active):.2f})")
fig.tight_layout(); fig.savefig(FIG / "gslc_scatter.png", dpi=180); plt.close(fig)

fig, ax = plt.subplots(figsize=(9, 4)); p = peers.sort_values("Info ratio")
ax.barh(p.index, p["Info ratio"], color=[NAVY if i == "GSLC" else GREY for i in p.index]); ax.axvline(0, color="k", lw=.6)
ax.set_title(f"Information ratio vs SPY since {start:%b %Y}: GSLC and factor-ETF peers"); fig.tight_layout(); fig.savefig(FIG / "gslc_peers.png", dpi=180); plt.close(fig)
print("charts done")

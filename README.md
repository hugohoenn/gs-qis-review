# GS QIS Product Review

Independent, public-data analysis of the public products run by Goldman Sachs Asset Management's Quantitative Investment
Strategies team, written the way a client portfolio manager would brief a client. Companion to the [multi-factor strategy](https://github.com/hugohoenn/factor-strategy) repo, whose data pipeline this reuses.

| Part | Product | Question | Headline |
|---|---|---|---|
| [1](docs/part1_gartx.md) | **Absolute Return Tracker (GARTX / GJRTX)** — hedge fund replication, since 2008 | What does it hold, can a client replicate it, what is it for? | 10 ETFs explain 89% of returns; an OOS ETF clone tracks it at 2.0% TE / 0.94 corr and earns the fee back; best of the liquid replicators, but 0.93 correlated with the S&P 500 |
| [2](docs/part2_gslc.md) | **ActiveBeta U.S. Large Cap (GSLC)** — four-factor smart beta, since 2015 | How much of the ETF can be rebuilt from the published rulebook, and what has it delivered? | Rulebook recovers ~0.40 correlation of active returns, stable out of sample; GSLC has trailed SPY by 0.9%/yr at 1.4% TE, driven by quality/low-vol tilts and a mega-cap underweight |

| [3](https://github.com/hugohoenn/macro-program) | **Managed Futures Strategy (GMSSX)** — trend following, since 2012 | How does a 21-market trend & carry program built from scratch compare, and does an ML overlay help? | Program: 0.41 Sharpe, −0.15 corr to S&P 500, positive in 2008/2020/2022; 0.63 correlated with GMSSX at a higher Sharpe; gradient-boosted overlay lost to the rule under purged walk-forward validation. Lives in its own repo. |

All three notes end with a section on what the analysis *cannot* tell you. Readable versions with charts: [hugohoenn.com/review](https://hugohoenn.com/review/).

## Layout
```
src/data.py            prices for funds, peers and the ETF factor basket
src/gartx.py           static/rolling/Kalman exposures, OOS ETF clone, FF regression, peers, stress
src/charts.py          Part 1 figures
src/gslc.py            rulebook replication of the ActiveBeta index; parameter fit 2015-20, test 2021-26
src/gslc_analysis.py   active-return comparison, attribution, peer table, Part 2 figures
src/xray.py            Fund X-ray: precomputes 45 funds for hugohoenn.com/xray
docs/                  the two notes            output/   tables (csv) and figures
```
Requires the `factor-strategy` repo's processed panels for Part 2. Licensed index data (e.g. HFRX) is never committed; only derived statistics are published.

*Hugo Hoenn, September 2026. Not affiliated with or endorsed by Goldman Sachs. Not investment advice.*

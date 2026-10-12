# %% [markdown]
# # Volatility Dynamics & the Fear Index: Nifty 50, India VIX and a VIX-timed put hedge
#
# Reproducible analysis for the FDRM assignment. Run top to bottom (`python fdrm_vix_analysis.py`
# or open the `.ipynb`). All outputs go to `figures/` and `output/`.
#
# Data (real, daily, Yahoo Finance series mirrored on GitHub because Yahoo/NSE were not
# reachable from the analysis machine):
# * `data/nifty50_daily_raw.csv`  : ^NSEI OHLC, 2007-09-17 to 2026-04-13
#   (github.com/kalilurrahman/NIFTY_50_STOCK_DATA, NIFTY50_stock_history.csv)
# * `data/india_vix_daily_raw.csv`: ^INDIAVIX OHLC, 2020-01-02 to 2026-08-24
#   (github.com/tanya459/india-vix-market-data-analysis, Dataset/IndiaVIX_Cleaned_Dataset.csv)
#
# Spot checks against NSE published closes: Nifty 4-Jun-2024 = 21,884.50; India VIX 4-Jun-2024 = 26.75.
#
# Historical Nifty option-chain prices are not in the data, so option premiums are MODELLED with
# Black-Scholes-Merton using India VIX as the implied volatility, plus a put-skew add-on and a
# bid/ask haircut. Every assumption is a parameter in the next cell.

# %%
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DATA, FIG, OUT = ROOT / "data", ROOT / "figures", ROOT / "output"
FIG.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# ---- assumptions -------------------------------------------------------------------
R = 0.065            # risk-free (approx. 91-day T-bill), continuous
Q = 0.013            # Nifty dividend yield
SKEW_PER_PCT = 0.6   # extra put IV, in vol points, per 1% out-of-the-money (5% OTM -> +3 pts)
HALF_SPREAD = 0.5    # bid/ask half-spread in vol points (buy at IV+0.5, sell at IV-0.5)
LOW_VIX, HIGH_VIX = 13.0, 20.0   # regime cut-offs (~30th / ~80th percentile of 2020-26 VIX)
SPIKE_1, SPIKE_2 = 22.0, 30.0    # spike triggers (VIX>=22 = top ~15% of days; 30 = second rung of fixed ladder)
TRAIL = 0.20                     # trailing rule: sell the rest once VIX is 20% below its post-spike peak
TENOR = 3                        # proposed hedge: 3-month put, rolled monthly
PUT_MONEYNESS = 0.95             # 5% OTM put
SPREAD_SHORT = 0.85              # short leg of the put spread baseline
TRADING_DAYS = 252

# Palette (validated reference categorical order)
C = dict(blue="#2a78d6", orange="#eb6834", aqua="#1baf7a", yellow="#eda100",
         magenta="#e87ba4", green="#008300", violet="#4a3aa7", red="#e34948",
         ink="#0b0b0b", ink2="#52514e", grid="#e4e3df")
REGIME_COL = {"Low": "#cfe3f7", "Normal": "#f1f0ec", "High": "#fbd9cb"}
plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9.5, "axes.edgecolor": C["ink2"],
    "axes.labelcolor": C["ink2"], "xtick.color": C["ink2"], "ytick.color": C["ink2"],
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": C["grid"], "grid.linewidth": 0.6, "lines.linewidth": 1.6,
    "axes.titleweight": "bold", "axes.titlesize": 10.5, "legend.frameon": False,
})
RESULTS = {}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# %% [markdown]
# ## 1. Load and align data

# %%
nifty = pd.read_csv(DATA / "nifty50_daily_raw.csv", parse_dates=["Date"]).set_index("Date")
nifty = nifty[["Open", "High", "Low", "Close"]].astype(float)
nifty = nifty[~nifty.index.duplicated()].sort_index()

vix_raw = pd.read_csv(DATA / "india_vix_daily_raw.csv", encoding="utf-8-sig", parse_dates=["Date"])
vix = vix_raw.rename(columns={"Sum of Open": "VIX_Open", "Sum of High": "VIX_High",
                              "Sum of Low": "VIX_Low", "Sum of Close": "VIX"})
vix = vix.set_index("Date")[["VIX_Open", "VIX_High", "VIX_Low", "VIX"]].astype(float).sort_index()

nifty["ret"] = np.log(nifty.Close).diff()
nifty["rv21_trail"] = nifty.ret.rolling(21).std() * math.sqrt(TRADING_DAYS) * 100
# realised vol over the NEXT 21 trading days (what VIX is trying to forecast)
nifty["rv21_fwd"] = nifty.ret[::-1].rolling(21).std()[::-1].shift(-1) * math.sqrt(TRADING_DAYS) * 100
nifty["fwd21"] = nifty.Close.shift(-21) / nifty.Close - 1
nifty["fwd63"] = nifty.Close.shift(-63) / nifty.Close - 1
nifty["fwd1"] = nifty.ret.shift(-1)

df = nifty.join(vix, how="inner").dropna(subset=["Close", "VIX"])
df["dvix"] = np.log(df.VIX).diff()
df["regime"] = pd.cut(df.VIX, [0, LOW_VIX, HIGH_VIX, 1e9], labels=["Low", "Normal", "High"])
df.to_csv(OUT / "nifty_vix_merged.csv")
RESULTS["sample"] = dict(start=str(df.index.min().date()), end=str(df.index.max().date()), days=len(df),
                         vix_pct=df.VIX.quantile([.1, .3, .5, .8, .9]).round(2).to_dict(),
                         regime_share=df.regime.value_counts(normalize=True).round(3).to_dict())
print(RESULTS["sample"])

# %% [markdown]
# ## 2. How India VIX is built (NSE methodology) and a numerical check
#
# India VIX uses the CBOE model-free formula on NIFTY near- and next-month OTM option quotes:
# sigma^2 = (2/T) * sum(dK/K^2 * e^{RT} * Q(K)) - (1/T) * (F/K0 - 1)^2, computed for both expiries
# and interpolated to a constant 30-calendar-day horizon; VIX = 100 * sqrt(sigma^2_30).
# Below we price a synthetic chain with Black-Scholes and push it through that formula: with a flat
# 15% smile the index returns ~15; with put skew it returns MORE than ATM IV, which is why VIX also
# prices crash fear.


# %%
def bs_put(S, K, T, sigma, r=R, q=Q):
    T = np.maximum(T, 1e-8)
    sigma = np.maximum(sigma, 1e-4)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


def bs_call(S, K, T, sigma, r=R, q=Q):
    return bs_put(S, K, T, sigma, r, q) + S * np.exp(-q * T) - K * np.exp(-r * T)


def put_iv(vix_level, S, K):
    """India VIX + linear put skew, as a decimal vol."""
    otm_pct = np.maximum(0.0, (1 - K / S) * 100)
    return (vix_level + SKEW_PER_PCT * otm_pct) / 100


def model_free_var(S, T, iv_fn, r=R, q=Q, step=50):
    F = S * math.exp((r - q) * T)
    Ks = np.arange(round(S * 0.6 / step) * step, round(S * 1.4 / step) * step + step, step, dtype=float)
    K0 = Ks[Ks <= F].max()
    Qk = np.where(Ks < K0, bs_put(S, Ks, T, iv_fn(Ks)),
                  np.where(Ks > K0, bs_call(S, Ks, T, iv_fn(Ks)),
                           0.5 * (bs_put(S, Ks, T, iv_fn(Ks)) + bs_call(S, Ks, T, iv_fn(Ks)))))
    dK = np.gradient(Ks)
    return (2 / T) * np.sum(dK / Ks ** 2 * math.exp(r * T) * Qk) - (1 / T) * (F / K0 - 1) ** 2


def india_vix_formula(S, iv_fn, d_near=16, d_next=44):
    T1, T2 = d_near / 365, d_next / 365
    v1, v2 = model_free_var(S, T1, iv_fn), model_free_var(S, T2, iv_fn)
    N30 = 30 / 365
    w = (T2 - N30) / (T2 - T1)
    return 100 * math.sqrt((T1 * v1 * w + T2 * v2 * (1 - w)) / N30)


S0 = 24000.0
flat = india_vix_formula(S0, lambda K: np.full_like(K, 0.15))
skew = india_vix_formula(S0, lambda K: 0.15 + 0.006 * np.maximum(0, (1 - K / S0) * 100)
                         - 0.002 * np.maximum(0, (K / S0 - 1) * 100))
RESULTS["vix_construction"] = dict(flat15=round(flat, 2), skewed_atm15=round(skew, 2))
print(RESULTS["vix_construction"])

# %% [markdown]
# ## 3. Implied vs realised volatility: the volatility risk premium (VRP)
# VRP_t = India VIX_t - realised Nifty vol over the following 21 trading days (annualised).

# %%
v = df.dropna(subset=["rv21_fwd"]).copy()
v["vrp"] = v.VIX - v.rv21_fwd
vrp_stats = dict(
    mean_vix=v.VIX.mean(), mean_rv_fwd=v.rv21_fwd.mean(), mean_vrp=v.vrp.mean(), median_vrp=v.vrp.median(),
    share_positive=(v.vrp > 0).mean(),
    corr_vix_rvfwd=v[["VIX", "rv21_fwd"]].corr().iloc[0, 1],
    corr_vix_rvtrail=v[["VIX", "rv21_trail"]].corr().iloc[0, 1],
)
# Newey-West t-stat for the mean VRP (21-day overlap)
nw = sm.OLS(v.vrp.values, np.ones(len(v))).fit(cov_type="HAC", cov_kwds={"maxlags": 21})
vrp_stats["nw_t_mean_vrp"] = float(nw.tvalues[0])
by_reg = v.groupby("regime", observed=True).agg(VIX=("VIX", "mean"), RV_fwd=("rv21_fwd", "mean"),
                                                VRP=("vrp", "mean"), VRP_pos=("vrp", lambda x: (x > 0).mean()),
                                                days=("vrp", "size"))
by_reg.round(3).to_csv(OUT / "vrp_by_regime.csv")
# Mincer-Zarnowitz forecast regression: RV_fwd = a + b*VIX
mz = sm.OLS(v.rv21_fwd, sm.add_constant(v.VIX)).fit(cov_type="HAC", cov_kwds={"maxlags": 21})
vrp_stats.update(mz_alpha=float(mz.params.iloc[0]), mz_beta=float(mz.params.iloc[1]), mz_r2=float(mz.rsquared))
RESULTS["vrp"] = {k: round(float(x), 3) for k, x in vrp_stats.items()}
RESULTS["vrp_by_regime"] = by_reg.round(2).reset_index().to_dict(orient="records")
print(RESULTS["vrp"]); print(by_reg.round(2))

fig, ax = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
ax[0].plot(v.index, v.VIX, color=C["blue"], label="India VIX (implied, 30-day)")
ax[0].plot(v.index, v.rv21_fwd, color=C["orange"], lw=1.2, label="Realised vol, next 21 trading days")
ax[0].set_ylabel("Annualised vol (%)"); ax[0].set_ylim(0, 90); ax[0].legend(loc="upper right")
ax[0].set_title("Implied (India VIX) vs subsequently realised Nifty volatility")
ax[1].fill_between(v.index, v.vrp, 0, where=v.vrp >= 0, color=C["blue"], alpha=.55, lw=0, label="VIX > realised")
ax[1].fill_between(v.index, v.vrp, 0, where=v.vrp < 0, color=C["red"], alpha=.65, lw=0, label="Realised > VIX")
ax[1].axhline(0, color=C["ink2"], lw=.8); ax[1].set_ylabel("VRP (vol pts)"); ax[1].set_ylim(-35, 25)
ax[1].legend(loc="lower right", ncol=2)
save(fig, "fig2_vrp.png")

# %% [markdown]
# ## 4. VIX regimes and Nifty returns

# %%
reg_rows = []
for reg, g in df.groupby("regime", observed=True):
    for h, col in [("1d", "fwd1"), ("21d", "fwd21"), ("63d", "fwd63")]:
        x = g[col].dropna()
        lag = {"1d": 1, "21d": 21, "63d": 63}[h]
        m = sm.OLS(x.values, np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
        reg_rows.append(dict(regime=reg, horizon=h, n=len(x), mean_pct=x.mean() * 100, median_pct=x.median() * 100,
                             sd_pct=x.std() * 100, hit_rate=(x > 0).mean(), nw_t=float(m.tvalues[0]),
                             p5_pct=x.quantile(.05) * 100))
reg_tab = pd.DataFrame(reg_rows)
reg_tab.round(3).to_csv(OUT / "returns_by_regime.csv", index=False)

same_day = df.groupby("regime", observed=True).ret.agg(
    mean_pct=lambda x: x.mean() * 100, sd_pct=lambda x: x.std() * 100,
    ann_vol=lambda x: x.std() * math.sqrt(TRADING_DAYS) * 100,
    worst_pct=lambda x: x.min() * 100, days="size")
same_day.round(3).to_csv(OUT / "sameday_by_regime.csv")

kw21 = stats.kruskal(*[g.fwd21.dropna() for _, g in df.groupby("regime", observed=True)])
lev21 = stats.levene(*[g.fwd21.dropna() for _, g in df.groupby("regime", observed=True)])
kw1 = stats.kruskal(*[g.ret.dropna() for _, g in df.groupby("regime", observed=True)])
lev1 = stats.levene(*[g.ret.dropna() for _, g in df.groupby("regime", observed=True)])
xy = df[["ret", "dvix"]].dropna()
corr = xy.corr().iloc[0, 1]
up, dn = xy[xy.ret > 0], xy[xy.ret < 0]
beta = sm.OLS(xy.dvix, sm.add_constant(xy.ret)).fit()
pred = sm.OLS(df.fwd21.dropna(), sm.add_constant(df.loc[df.fwd21.notna(), "VIX"])).fit(
    cov_type="HAC", cov_kwds={"maxlags": 21})
RESULTS["regimes"] = dict(
    kruskal_fwd21_p=kw21.pvalue, levene_fwd21_p=lev21.pvalue, kruskal_daily_p=kw1.pvalue, levene_daily_p=lev1.pvalue,
    corr_ret_dlogvix=corr, beta_dlogvix_on_ret=float(beta.params.iloc[1]),
    mean_dlogvix_on_down_days=dn.dvix.mean(), mean_dlogvix_on_up_days=up.dvix.mean(),
    fwd21_on_vix_slope_pct_per_pt=float(pred.params.iloc[1] * 100), fwd21_on_vix_t=float(pred.tvalues.iloc[1]))
RESULTS["regimes"] = {k: float(round(x, 4)) for k, x in RESULTS["regimes"].items()}
RESULTS["returns_by_regime"] = reg_tab.round(3).to_dict(orient="records")
RESULTS["sameday_by_regime"] = same_day.round(3).reset_index().to_dict(orient="records")
print(reg_tab.round(3)); print(same_day.round(3)); print(RESULTS["regimes"])

# Figure 1: Nifty and VIX with regimes
fig, ax = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, gridspec_kw={"height_ratios": [1.3, 1]})
seg = (df.regime != df.regime.shift()).cumsum()
for _, g in df.groupby(seg):
    for a in ax:
        a.axvspan(g.index[0], g.index[-1] + pd.Timedelta(days=1), color=REGIME_COL[str(g.regime.iloc[0])], lw=0, zorder=0)
ax[0].plot(df.index, df.Close, color=C["ink"], lw=1.1); ax[0].set_ylabel("Nifty 50")
ax[0].set_title("Nifty 50 and India VIX, shaded by VIX regime (blue = Low <13, grey = Normal, orange = High >20)")
ax[1].plot(df.index, df.VIX, color=C["blue"], lw=1.1); ax[1].set_ylabel("India VIX"); ax[1].set_ylim(0, 90)
for lvl in (LOW_VIX, HIGH_VIX):
    ax[1].axhline(lvl, color=C["ink2"], lw=.7, ls="--")
for d, lab in [("2020-03-24", "COVID"), ("2022-02-24", "Ukraine"), ("2024-06-04", "Election\nresult"),
               ("2025-04-07", "US tariffs")]:
    d = pd.Timestamp(d); y = df.VIX.asof(d)
    ax[1].annotate(lab, (d, y), xytext=(0, 12), textcoords="offset points", ha="center", fontsize=8, color=C["ink2"])
save(fig, "fig1_nifty_vix_regimes.png")

# Figure 3: regime returns + leverage-effect scatter
fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.8))
t21 = reg_tab[reg_tab.horizon == "21d"].set_index("regime")
cols = [C["blue"], C["ink2"], C["orange"]]
ax[0].bar(t21.index.astype(str), t21.mean_pct, color=cols, width=.55)
err = 1.96 * t21.mean_pct / t21.nw_t
ax[0].errorbar(range(3), t21.mean_pct, yerr=err.abs(), fmt="none", ecolor=C["ink"], capsize=4, lw=1)
for i, (m, sd) in enumerate(zip(t21.mean_pct, t21.sd_pct)):
    ax[0].text(i, -0.3, f"sd {sd:.1f}%", ha="center", va="top", fontsize=8, color=C["ink2"])
ax[0].axhline(0, color=C["ink2"], lw=.8)
ax[0].set_title("Next-21-day Nifty return by VIX regime\n(mean, 95% Newey-West CI)"); ax[0].set_ylabel("%")
ax[1].scatter(xy.ret * 100, xy.dvix * 100, s=8, color=C["blue"], alpha=.35, lw=0)
xs = np.linspace(xy.ret.min(), xy.ret.max(), 50)
ax[1].plot(xs * 100, (beta.params.iloc[0] + beta.params.iloc[1] * xs) * 100, color=C["orange"])
ax[1].set_xlabel("Nifty daily log return (%)"); ax[1].set_ylabel("Daily change in log VIX (%)")
ax[1].set_title(f"VIX rises when Nifty falls (corr {corr:.2f})")
save(fig, "fig3_regime_returns.png")

# %% [markdown]
# ## 5. Option premiums around high-uncertainty events: 4 June 2024 election results
# Modelled premiums: constant-maturity 30-day ATM straddle (% of spot) and the June-2024 monthly
# contract (expiry Thu 27-Jun-2024) 22,500 put, both priced off India VIX (+ skew for the put).

# %%
def straddle_pct(vix_level, days=30):
    T = days / 365; s = vix_level / 100
    return (bs_put(1.0, 1.0, T, s) + bs_call(1.0, 1.0, T, s)) * 100


df["straddle30"] = straddle_pct(df.VIX)
df["implied_daily_move"] = df.VIX / math.sqrt(365) * math.sqrt(365 / TRADING_DAYS)  # VIX per trading day, %
df["abs_ret"] = df.ret.abs() * 100

win = df.loc["2024-04-01":"2024-07-15"].copy()
exp_jun = pd.Timestamp("2024-06-27")
Kp = 22500.0
Tj = pd.Series(np.clip((exp_jun - win.index).days, 0, None) / 365, index=win.index)
win["put22500"] = np.where(win.index <= exp_jun, bs_put(win.Close.values, Kp, Tj.values,
                                                        put_iv(win.VIX.values, win.Close.values, Kp)), np.nan)

# Implied event-day move backed out of the VIX term premium (variance additivity):
# VIX_pre^2 * 30 = VIX_base^2 * 29 + event_var * 365  ->  event sd
base = df.loc["2024-01-01":"2024-03-31", "VIX"].median()
ev = {}
for d in ["2024-05-31", "2024-06-03"]:
    pre = float(df.VIX.loc[d])
    # VIX is in vol points, so the event-day sd comes out directly in %
    ev[d] = dict(vix=pre,
                 implied_event_sd_pct=round(math.sqrt(max((pre ** 2 * 30 - base ** 2 * 29) / 365, 0)), 2),
                 vix_only_daily_sd_pct=round(pre / math.sqrt(TRADING_DAYS), 2))

e = df.loc["2024-05-27":"2024-06-07", ["Close", "ret", "VIX", "straddle30", "implied_daily_move"]].copy()
e["ret_pct"] = (np.exp(e.ret) - 1) * 100
e["put22500"] = win.put22500.reindex(e.index)
e.round(3).to_csv(OUT / "election_window.csv")
intraday_low = (df.Low.loc["2024-06-04"] / df.Close.loc["2024-06-03"] - 1) * 100
normal = df.loc["2024-01-01":"2024-04-30"]
RESULTS["election"] = dict(
    base_vix_q1_2024=round(float(base), 2), events=ev,
    nifty_ret_4jun_pct=round(float(e.ret_pct.loc["2024-06-04"]), 2),
    nifty_ret_3jun_pct=round(float(e.ret_pct.loc["2024-06-03"]), 2),
    nifty_ret_5jun_pct=round(float(e.ret_pct.loc["2024-06-05"]), 2),
    intraday_low_4jun_pct=round(float(intraday_low), 2),
    vix_path={str(k.date()): round(float(x), 2) for k, x in e.VIX.items()},
    straddle30_path={str(k.date()): round(float(x), 2) for k, x in e.straddle30.items()},
    put22500_path={str(k.date()): round(float(x), 1) for k, x in e.put22500.items()},
    normal_jan_apr_2024=dict(vix_median=round(float(normal.VIX.median()), 2),
                             straddle30_median=round(float(normal.straddle30.median()), 2),
                             abs_ret_median=round(float(normal.abs_ret.median()), 2)),
    vix_min_apr_2024=round(float(df.loc["2024-04-01":"2024-04-30", "VIX"].min()), 2),
    vix_change_5jun_pct=round(float((df.VIX.loc["2024-06-05"] / df.VIX.loc["2024-06-04"] - 1) * 100), 1),
)
print(json.dumps(RESULTS["election"], indent=1))

# Cross-event comparison vs normal days
events = {"COVID crash (23-Mar-20)": "2020-03-23", "Ukraine invasion (24-Feb-22)": "2022-02-24",
          "Exit polls (3-Jun-24)": "2024-06-03", "Election result (4-Jun-24)": "2024-06-04",
          "Yen-carry unwind (5-Aug-24)": "2024-08-05", "US tariff crash (7-Apr-25)": "2025-04-07"}
rows = []
for name, d in events.items():
    d = pd.Timestamp(d); i = df.index.get_loc(d)
    pre = df.iloc[i - 1]; row = df.iloc[i]
    rows.append(dict(event=name, date=str(d.date()), nifty_ret_pct=(math.exp(row.ret) - 1) * 100,
                     vix_prev=pre.VIX, vix=row.VIX, vix_chg_pct=(row.VIX / pre.VIX - 1) * 100,
                     straddle_prev_pct=pre.straddle30, straddle_pct=row.straddle30,
                     move_vs_implied=abs(row.ret) * 100 / pre.implied_daily_move))
nd = df[(df.abs_ret < df.abs_ret.quantile(.9))]
rows.append(dict(event="Normal day (median, excl. top-10% moves)", date="", nifty_ret_pct=nd.abs_ret.median(),
                 vix_prev=nd.VIX.median(), vix=nd.VIX.median(), vix_chg_pct=(np.exp(nd.dvix.abs()) - 1).median() * 100,
                 straddle_prev_pct=nd.straddle30.median(), straddle_pct=nd.straddle30.median(),
                 move_vs_implied=(nd.abs_ret / nd.implied_daily_move.shift(1)).median()))
ev_tab = pd.DataFrame(rows)
ev_tab.round(2).to_csv(OUT / "event_comparison.csv", index=False)
RESULTS["event_table"] = ev_tab.round(2).to_dict(orient="records")
print(ev_tab.round(2))

# Generic event study: the 20 largest one-day VIX jumps vs all other days
top = df.dvix.nlargest(20).index
RESULTS["vix_jump_days"] = dict(
    n=20, mean_nifty_ret_pct=float(df.loc[top, "ret"].mean() * 100),
    mean_straddle_jump_pct_of_spot=float((df.straddle30 - df.straddle30.shift()).loc[top].mean()),
    mean_vix_jump_pct=float((np.exp(df.loc[top, "dvix"]) - 1).mean() * 100),
    other_days_mean_abs_ret=float(df.drop(top).abs_ret.mean()))

fig, ax = plt.subplots(3, 1, figsize=(9, 7), sharex=True, gridspec_kw={"height_ratios": [1.1, 1, 1]})
for a in ax:
    a.axvspan(pd.Timestamp("2024-06-04") - pd.Timedelta(hours=12), pd.Timestamp("2024-06-04") + pd.Timedelta(hours=12),
              color=REGIME_COL["High"], lw=0)
ax[0].plot(win.index, win.Close, color=C["ink"]); ax[0].set_ylabel("Nifty 50")
ax[0].set_title("Around the 4 June 2024 election result: spot, India VIX and modelled option premiums")
ax[0].annotate(f"4 Jun: {RESULTS['election']['nifty_ret_4jun_pct']}%", (pd.Timestamp("2024-06-04"), win.Close.loc["2024-06-04"]),
               xytext=(8, -4), textcoords="offset points", fontsize=8.5, color=C["ink2"])
ax[1].plot(win.index, win.VIX, color=C["blue"]); ax[1].set_ylabel("India VIX")
ax[1].axhline(RESULTS["election"]["normal_jan_apr_2024"]["vix_median"], color=C["ink2"], ls="--", lw=.8)
ax[1].text(win.index[2], RESULTS["election"]["normal_jan_apr_2024"]["vix_median"] + .6, "Jan-Apr 2024 median", fontsize=8, color=C["ink2"])
ax[2].plot(win.index, win.straddle30, color=C["orange"], label="30-day ATM straddle, % of spot")
ax2b = ax[2]
ax2b.set_ylabel("% of spot")
ax2b.legend(loc="upper left")
save(fig, "fig4_election_window.png")

fig, ax = plt.subplots(figsize=(9, 3.2))
ax.plot(win.index, win.put22500, color=C["magenta"])
ax.set_ylabel("Premium (index points)")
ax.set_title("Modelled premium of the NIFTY 27-Jun-2024 22,500 put (BSM, IV = India VIX + skew)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
save(fig, "fig5_put22500.png")

# %% [markdown]
# ## 6. Backtest: VIX-timed protective puts for a long-term Nifty portfolio
#
# Portfolio: 100% Nifty 50 (price index; dividends excluded for all strategies). Options are funded by
# selling Nifty units and all option cash (sale or expiry) is reinvested in Nifty the same day.
# Roll dates = first trading day of each month; option expiries are synthetic at a later roll date.
#
# Strategies
# * **Unhedged**
# * **Always 1M put**: every month buy a 1-month 5% OTM put on 100% of the portfolio, hold to expiry.
# * **Always 1M put spread**: buy 95% put / sell 85% put each month, hold to expiry.
# * **Always 3M put, rolled monthly**: same instrument as the proposal but bought every month regardless of VIX.
# * **VIX-timed 3M put, hold**: on a roll date, only if VIX < 13, sell the existing put and buy a fresh 3-month
#   5% OTM put. Otherwise keep what you hold until it expires. No early sale.
# * **VIX-timed 3M put + hybrid monetisation (proposed)**: as above, plus: sell half the puts the first day
#   VIX >= 22, and the other half once the spike fades (VIX 20% below its highest close since crossing 22).
#   Proceeds go straight back into Nifty ("buy the dip" with the insurance payout).
# * **VIX-timed 3M put, sell all at VIX 22**: single fixed-trigger variant.

# %%
bt = df.loc[:, ["Close", "VIX", "regime"]].copy()
dates = bt.index
first_of_month = pd.Series(dates, index=dates).groupby([dates.year, dates.month]).transform("min")
roll_dates = set(first_of_month.unique())
roll_list = sorted(roll_dates)


def next_roll(d, k):
    i = roll_list.index(d)
    return roll_list[i + k] if i + k < len(roll_list) else None


def run(strategy, low=LOW_VIX, spike1=SPIKE_1, spike2=SPIKE_2, tenor=TENOR, moneyness=PUT_MONEYNESS,
        skew=SKEW_PER_PCT, half_spread=HALF_SPREAD, tranche=1.0, stagger=False, trail=TRAIL):
    units = 1.0 / bt.Close.iloc[0]   # start with 1.0 of wealth in Nifty
    pos = []                          # dicts: K, exp, qty, sign(+1 long/-1 short), trade_id
    trades = []                       # hedge cashflow ledger
    rec = []
    tid = 0

    def iv(vixl, S, K, side):
        otm = max(0.0, (1 - K / S) * 100)
        return max((vixl + skew * otm + side * half_spread) / 100, 0.01)

    def price(p, d, S, vixl, side=0):
        T = (p["exp"] - d).days / 365
        if T <= 0:
            return max(p["K"] - S, 0.0)
        return float(bs_put(S, p["K"], T, iv(vixl, S, p["K"], side)))

    def close_pos(p, d, S, vixl, frac, reason, regime):
        nonlocal units
        q = p["qty"] * frac
        # selling a long put hits the bid (side -1); buying back a short put lifts the offer (+1)
        px = price(p, d, S, vixl, side=-1 if p["sign"] > 0 else +1)
        cash = p["sign"] * q * px
        units += cash / S
        p["qty"] -= q
        trades.append(dict(date=d, trade_id=p["tid"], action=reason, K=p["K"], qty=q * p["sign"], price=px,
                           cash=cash, vix=vixl, regime=regime, open_regime=p["open_regime"]))

    def open_pos(d, S, vixl, K, months, sign, regime, frac=1.0):
        nonlocal units, tid
        exp = next_roll(d, months)
        if exp is None:
            return
        V = units * S + sum(price(p, d, S, vixl) * p["qty"] * p["sign"] for p in pos)
        qty = frac * V / S
        p = dict(K=K, exp=exp, qty=qty, sign=sign, tid=tid, open_regime=regime, sold1=False)
        px = price(p, d, S, vixl, side=+1 if sign > 0 else -1)
        cash = -sign * qty * px
        units += cash / S
        pos.append(p)
        trades.append(dict(date=d, trade_id=tid, action="open", K=K, qty=qty * sign, price=px, cash=cash,
                           vix=vixl, regime=regime, open_regime=regime))
        tid += 1

    for d, row in bt.iterrows():
        S, vixl, regime = row.Close, row.VIX, str(row.regime)
        # 1) settle expiries
        for p in pos:
            if p["qty"] > 0 and p["exp"] <= d:
                close_pos(p, d, S, vixl, 1.0, "expiry", regime)
        pos = [p for p in pos if p["qty"] > 1e-12]
        is_roll = d in roll_dates
        # 2) strategy logic
        if strategy == "always_put" and is_roll:
            open_pos(d, S, vixl, round(S * moneyness / 50) * 50, 1, +1, regime)
        elif strategy == "always_spread" and is_roll:
            open_pos(d, S, vixl, round(S * moneyness / 50) * 50, 1, +1, regime)
            open_pos(d, S, vixl, round(S * SPREAD_SHORT / 50) * 50, 1, -1, regime)
        elif strategy.startswith("timed"):
            monetise = strategy in ("timed_ladder", "timed_all", "timed_trail", "timed_hybrid")
            if monetise:
                for p in pos:
                    # trailing rule: arm once VIX >= spike1, then sell when VIX has fallen
                    # `trail` (20%) from its highest close since arming, i.e. once the spike starts to fade
                    if strategy in ("timed_trail", "timed_hybrid"):
                        if vixl >= spike1:
                            p["peak"] = max(p.get("peak", 0.0), vixl)
                        if strategy == "timed_hybrid" and not p["sold1"] and vixl >= spike1:
                            close_pos(p, d, S, vixl, 0.5, "monetise_1", regime); p["sold1"] = True
                        if p.get("peak") and vixl <= (1 - trail) * p["peak"] and p["qty"] > 0:
                            close_pos(p, d, S, vixl, 1.0, "monetise_trail", regime)
                    elif strategy == "timed_ladder":
                        if not p["sold1"] and vixl >= spike1:
                            close_pos(p, d, S, vixl, 0.5, "monetise_1", regime); p["sold1"] = True
                        if p["sold1"] and vixl >= spike2 and p["qty"] > 0:
                            close_pos(p, d, S, vixl, 1.0, "monetise_2", regime)
                    elif vixl >= spike1:
                        close_pos(p, d, S, vixl, 1.0, "monetise", regime)
                pos = [p for p in pos if p["qty"] > 1e-12]
            if is_roll and vixl < low:
                if not stagger:   # replace the old put with a fresh one
                    for p in pos:
                        close_pos(p, d, S, vixl, 1.0, "roll_sell", regime)
                    pos = []
                # stagger=True: keep older tranches and add a new one (overlapping expiries)
                open_pos(d, S, vixl, round(S * moneyness / 50) * 50, tenor, +1, regime, frac=tranche)
        hedge_mtm = sum(price(p, d, S, vixl) * p["qty"] * p["sign"] for p in pos)
        rec.append(dict(date=d, equity=units * S, hedge=hedge_mtm, value=units * S + hedge_mtm,
                        notional_hedged=sum(p["qty"] * p["sign"] for p in pos if p["sign"] > 0) * S))
    out = pd.DataFrame(rec).set_index("date")
    return out, pd.DataFrame(trades)


def metrics(val, rf=R):
    r = val.pct_change().dropna()
    yrs = (val.index[-1] - val.index[0]).days / 365.25
    cagr = (val.iloc[-1] / val.iloc[0]) ** (1 / yrs) - 1
    vol = r.std() * math.sqrt(TRADING_DAYS)
    dd = val / val.cummax() - 1
    downside = r[r < 0].std() * math.sqrt(TRADING_DAYS)
    return dict(final=val.iloc[-1], CAGR=cagr * 100, vol=vol * 100, sharpe=(cagr - rf) / vol,
                sortino=(cagr - rf) / downside, maxDD=dd.min() * 100, calmar=cagr / abs(dd.min()),
                worst_day=r.min() * 100, worst_21d=(val / val.shift(21) - 1).min() * 100)


PROPOSED = "VIX-timed 3M put + hybrid monetisation (proposed)"
STRATS = {"Unhedged": ("unhedged", {}), "Always 1M 95% put": ("always_put", {}),
          "Always 1M 95/85 put spread": ("always_spread", {}),
          "Always 3M 95% put, rolled monthly": ("timed_hold", {"low": 1e9}),
          "VIX-timed 3M put, hold": ("timed_hold", {}),
          PROPOSED: ("timed_hybrid", {}),
          "VIX-timed 3M put, sell all at VIX 22": ("timed_all", {})}
SLUG = {n: f"s{i}_{s}" for i, (n, (s, _)) in enumerate(STRATS.items())}
runs, ledgers = {}, {}
for name, (s, kw) in STRATS.items():
    runs[name], ledgers[name] = run(s, **kw)
vals = pd.DataFrame({k: r.value for k, r in runs.items()})
vals.to_csv(OUT / "backtest_values.csv")
perf = pd.DataFrame({k: metrics(vals[k]) for k in vals}).T
yrs = (vals.index[-1] - vals.index[0]).days / 365.25
for name, led in ledgers.items():
    if len(led) == 0:
        perf.loc[name, ["premium_paid_pa", "recovered_pa", "net_hedge_cost_pa", "share_time_hedged"]] = 0
        continue
    led.to_csv(OUT / f"ledger_{SLUG[name]}.csv", index=False)
    # express each cashflow as % of portfolio value on that date
    pv = vals[name].reindex(led.date).values
    led["cash_pct"] = led.cash.values / pv * 100
    paid = -led.loc[led.cash < 0, "cash_pct"].sum()
    rec_ = led.loc[led.cash > 0, "cash_pct"].sum()
    perf.loc[name, "premium_paid_pa"] = paid / yrs
    perf.loc[name, "recovered_pa"] = rec_ / yrs
    perf.loc[name, "net_hedge_cost_pa"] = (paid - rec_) / yrs
    perf.loc[name, "share_time_hedged"] = (runs[name].notional_hedged > 0).mean() * 100
perf = perf.fillna(0)
perf.round(3).to_csv(OUT / "backtest_performance.csv")
RESULTS["backtest_period"] = dict(start=str(vals.index[0].date()), end=str(vals.index[-1].date()), years=round(yrs, 2))
RESULTS["performance"] = perf.round(3).reset_index().rename(columns={"index": "strategy"}).to_dict(orient="records")
print(perf.round(2).to_string())

# %% [markdown]
# ### Cost and payoff across VIX regimes

# %%
regime_rows = []
for name in list(STRATS)[1:]:
    led = ledgers[name].copy()
    pv = vals[name].reindex(led.date).values
    led["cash_pct"] = led.cash.values / pv * 100
    # attribute every cashflow to the regime the trade was OPENED in, and separately the regime on the cash date
    for basis in ("open_regime", "regime"):
        g = led.groupby(basis)
        for reg in ["Low", "Normal", "High"]:
            if reg not in g.groups:
                regime_rows.append(dict(strategy=name, basis=basis, regime=reg, paid=0.0, received=0.0, net=0.0, n_trades=0))
                continue
            x = g.get_group(reg)
            paid = -x.loc[x.cash < 0, "cash_pct"].sum(); recv = x.loc[x.cash > 0, "cash_pct"].sum()
            regime_rows.append(dict(strategy=name, basis=basis, regime=reg, paid=paid, received=recv, net=recv - paid,
                                    n_trades=int((x.action == "open").sum())))
reg_cost = pd.DataFrame(regime_rows)
reg_cost.round(3).to_csv(OUT / "hedge_cost_payoff_by_regime.csv", index=False)
RESULTS["cost_by_regime"] = reg_cost.round(2).to_dict(orient="records")

# daily strategy return minus unhedged, split by the regime of the day (where does the hedge earn/cost?)
dr = vals.pct_change()
bt["regime_prev"] = bt.regime.shift()
excess = dr.sub(dr["Unhedged"], axis=0).join(bt.regime_prev)
regime_excess = (excess.groupby("regime_prev", observed=True).sum() * 100).drop(columns="Unhedged")
days_in = excess.groupby("regime_prev", observed=True).size()
regime_excess_pa = regime_excess.div(days_in, axis=0) * TRADING_DAYS
regime_excess.round(2).to_csv(OUT / "excess_return_by_regime_cumulative.csv")
regime_excess_pa.round(2).to_csv(OUT / "excess_return_by_regime_annualised.csv")
RESULTS["excess_by_regime_cum"] = regime_excess.round(2).to_dict()
RESULTS["excess_by_regime_pa"] = regime_excess_pa.round(2).to_dict()
print(regime_excess.round(2)); print(regime_excess_pa.round(2))

# episode table: drawdown windows
episodes = {"COVID crash (17-Jan to 23-Mar-20)": ("2020-01-17", "2020-03-23"),
            "2022 war/rates (17-Jan to 17-Jun-22)": ("2022-01-17", "2022-06-17"),
            "Election result day (3 to 4-Jun-24)": ("2024-06-03", "2024-06-04"),
            "Yen-carry unwind (1 to 5-Aug-24)": ("2024-08-01", "2024-08-05"),
            "Sep-24 to Mar-25 correction": ("2024-09-26", "2025-03-04"),
            "Apr-25 tariff shock (28-Mar to 7-Apr)": ("2025-03-28", "2025-04-07"), "Full period": (str(vals.index[0].date()), str(vals.index[-1].date()))}
ep = pd.DataFrame({k: (vals.loc[b] / vals.loc[a] - 1) * 100 for k, (a, b) in
                   ((k, (vals.index[vals.index.get_indexer([pd.Timestamp(a)], method="bfill")[0]],
                         vals.index[vals.index.get_indexer([pd.Timestamp(b)], method="ffill")[0]])) for k, (a, b) in episodes.items())}).T
ep.round(2).to_csv(OUT / "episode_returns.csv")
RESULTS["episodes"] = ep.round(2).to_dict(orient="index")
print(ep.round(2).to_string())

# trade-level summary of the proposed strategy
L = ledgers[PROPOSED]
tr = L.groupby("trade_id").agg(open_date=("date", "first"), open_vix=("vix", "first"), cash=("cash", "sum"),
                                exit=("action", lambda a: ",".join(sorted(set(a) - {"open"}))))
RESULTS["proposed_trades"] = dict(n=len(tr), winners=int((tr.cash > 0).sum()),
                                  monetised=int(tr.exit.str.contains("monetise").sum()),
                                  best=tr.sort_values("cash").tail(3).reset_index().assign(open_date=lambda x: x.open_date.astype(str)).round(5).to_dict(orient="records"))
monet = L[L.action.str.startswith("monetise")].copy()
monet["date"] = monet.date.astype(str)
RESULTS["proposed_monetisations"] = monet[["date", "action", "K", "price", "vix"]].round(2).to_dict(orient="records")

# %% [markdown]
# ### Charts

# %%
order = list(STRATS)
colors = [C["ink"], C["orange"], C["yellow"], C["magenta"], C["aqua"], C["blue"], C["violet"]]
fig, ax = plt.subplots(2, 1, figsize=(9, 6.2), sharex=True, gridspec_kw={"height_ratios": [1.6, 1]})
for n, c in zip(order, colors):
    lw = 2.0 if "proposed" in n or n == "Unhedged" else 1.2
    ax[0].plot(vals.index, vals[n], color=c, lw=lw, label=n)
    ax[1].plot(vals.index, (vals[n] / vals[n].cummax() - 1) * 100, color=c, lw=lw)
ax[0].set_ylabel("Growth of 1 (price index)"); ax[0].legend(loc="upper left", fontsize=8)
ax[0].set_title(f"Backtest {RESULTS['backtest_period']['start']} to {RESULTS['backtest_period']['end']}: hedged vs unhedged Nifty")
ax[1].set_ylabel("Drawdown (%)")
save(fig, "fig6_backtest_equity.png")

fig, ax = plt.subplots(figsize=(9, 3.6))
sub = reg_cost[reg_cost.basis == "open_regime"]
names = order[1:]
xx = np.arange(3); w = 0.13
for i, (n, c) in enumerate(zip(names, colors[1:])):
    s = sub[sub.strategy == n].set_index("regime").reindex(["Low", "Normal", "High"])
    ax.bar(xx + (i - 2.5) * w, s.net / yrs, width=w * 0.9, color=c, label=n)
ax.axhline(0, color=C["ink2"], lw=.8)
ax.set_xticks(xx, ["Bought in Low VIX (<13)", "Bought in Normal VIX", "Bought in High VIX (>20)"])
ax.set_ylabel("Net hedge P&L, % of portfolio p.a.")
ax.set_title("Where the hedge money goes: net option P&L by VIX regime at purchase")
ax.legend(fontsize=7.5, ncol=2, loc="lower left")
save(fig, "fig7_cost_by_regime.png")

# %% [markdown]
# ## 7. Robustness: buy threshold x monetisation threshold, and pricing assumptions

# %%
grid = []
for low in [12, 13, 14, 15, 16, 1e9]:
    for s1 in [20, 22, 25, 30]:
        o, _ = run("timed_hybrid", low=low, spike1=s1)
        m = metrics(o.value)
        grid.append(dict(buy_below=str(int(low)) if low < 100 else "always", spike1=s1, CAGR=m["CAGR"], maxDD=m["maxDD"],
                         sharpe=m["sharpe"], calmar=m["calmar"]))
grid = pd.DataFrame(grid)
grid.round(3).to_csv(OUT / "sensitivity_thresholds.csv", index=False)
RESULTS["sensitivity_thresholds"] = grid.round(2).to_dict(orient="records")

sens = []
for sk in [0.0, 0.6, 1.0]:
    for hs in [0.0, 0.5, 1.0]:
        for strat in ["always_put", "timed_hybrid"]:
            o, _ = run(strat, skew=sk, half_spread=hs)
            m = metrics(o.value)
            sens.append(dict(strategy=strat, skew_per_pct=sk, half_spread=hs, CAGR=m["CAGR"], maxDD=m["maxDD"]))
for ten in [1, 2, 3, 6]:
    o, _ = run("timed_hybrid", tenor=ten); m = metrics(o.value)
    sens.append(dict(strategy=f"proposed, tenor {ten}M", skew_per_pct=SKEW_PER_PCT, half_spread=HALF_SPREAD,
                     CAGR=m["CAGR"], maxDD=m["maxDD"]))
for mny in [0.90, 0.95, 1.00]:
    o, _ = run("timed_hybrid", moneyness=mny); m = metrics(o.value)
    sens.append(dict(strategy=f"proposed, strike {int(mny*100)}%", skew_per_pct=SKEW_PER_PCT, half_spread=HALF_SPREAD,
                     CAGR=m["CAGR"], maxDD=m["maxDD"]))
sens = pd.DataFrame(sens)
sens.round(3).to_csv(OUT / "sensitivity_pricing.csv", index=False)
RESULTS["sensitivity_pricing"] = sens.round(2).to_dict(orient="records")
# monetisation rule x tenor matrix (does the conclusion depend on one design choice?)
RULES = {"Hold to expiry": "timed_hold", "Sell all at VIX 22": "timed_all", "Ladder 22 / 30": "timed_ladder",
         "Trailing (fade 20%)": "timed_trail", "Hybrid (proposed)": "timed_hybrid"}
mat = []
for ten, tr, st, lab in [(2, 1, False, "2M rolled"), (3, 1, False, "3M rolled"), (3, 1 / 3, True, "3M staggered thirds"),
                         (6, 1 / 6, True, "6M staggered sixths")]:
    for rn, rs in RULES.items():
        o, _ = run(rs, tenor=ten, tranche=tr, stagger=st)
        m, mp = metrics(o.value), metrics(o.value.loc["2020-07-01":])
        mat.append(dict(structure=lab, rule=rn, CAGR=m["CAGR"], maxDD=m["maxDD"], sharpe=m["sharpe"],
                        covid=(o.value.asof(pd.Timestamp("2020-03-23")) / o.value.asof(pd.Timestamp("2020-01-17")) - 1) * 100,
                        CAGR_ex_covid=mp["CAGR"], maxDD_ex_covid=mp["maxDD"]))
mat = pd.DataFrame(mat)
mat.round(2).to_csv(OUT / "sensitivity_rule_by_tenor.csv", index=False)
RESULTS["rule_by_tenor"] = mat.round(2).to_dict(orient="records")
print(mat.round(2).to_string())
# start-date robustness: drop the COVID crash
post = vals.loc["2020-07-01":]
RESULTS["ex_covid_performance"] = {k: {kk: round(float(vv), 3) for kk, vv in metrics(post[k]).items()} for k in post}
print(grid.round(2).to_string()); print(sens.round(2).to_string())

fig, ax = plt.subplots(1, 2, figsize=(9.5, 3.4))
for a, col, title in [(ax[0], "CAGR", "CAGR (%)"), (ax[1], "maxDD", "Max drawdown (%)")]:
    h = grid.pivot(index="buy_below", columns="spike1", values=col)
    h = h.reindex(sorted(h.index, key=lambda x: 1e9 if x == "always" else float(x)))
    good = h.values                                          # higher CAGR / shallower drawdown = darker
    norm_ = (good - good.min()) / (np.ptp(good) + 1e-9)
    a.imshow(norm_, cmap="Blues", aspect="auto", vmin=-0.15, vmax=1.15)
    a.set_xticks(range(h.shape[1]), [f"{c:g}" for c in h.columns]); a.set_yticks(range(h.shape[0]), h.index)
    a.set_xlabel("First monetisation trigger (VIX)"); a.set_ylabel("Buy only if VIX below")
    a.grid(False); a.set_title(title + " (darker = better)")
    for i in range(h.shape[0]):
        for j in range(h.shape[1]):
            a.text(j, i, f"{h.values[i, j]:.1f}", ha="center", va="center", fontsize=8,
                   color="white" if norm_[i, j] > 0.6 else C["ink"])
unh = perf.loc["Unhedged"]
fig.suptitle(f"Proposed strategy sensitivity (Unhedged: CAGR {unh.CAGR:.1f}%, max DD {unh.maxDD:.1f}%)", fontsize=10, fontweight="bold")
save(fig, "fig8_sensitivity.png")

# %%
with open(OUT / "results.json", "w") as f:
    json.dump(RESULTS, f, indent=1, default=str)
print("done")

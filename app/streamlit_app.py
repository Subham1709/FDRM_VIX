"""Nifty 50, India VIX and a VIX-timed put hedge: a read-only web app.

Every number and series here is read from files that fdrm_vix_analysis.py already
saved in output/. The app does not re-run the backtest; it only rebases the saved
equity curves when you pick a later start date.

Run locally from the repo root:  streamlit run app/streamlit_app.py
"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
FIG = ROOT / "figures"
REPO_URL = "https://github.com/Subham1709/FDRM_VIX"

PROPOSED = "VIX-timed 3M put + hybrid monetisation (proposed)"
REGIME_ORDER = ["Low", "Normal", "High"]
REGIME_COLOURS = ["#2c7bb6", "#bdbdbd", "#d7191c"]

st.set_page_config(page_title="India VIX and a timed put hedge", page_icon="📉", layout="wide")


@st.cache_data
def load_csv(name, **kw):
    return pd.read_csv(OUT / name, **kw)


@st.cache_data
def load_results():
    return json.loads((OUT / "results.json").read_text())


R = load_results()
perf = load_csv("backtest_performance.csv", index_col=0)
values = load_csv("backtest_values.csv", parse_dates=["date"]).set_index("date")
market = load_csv("nifty_vix_merged.csv", parse_dates=["Date"])
vrp_regime = load_csv("vrp_by_regime.csv")
sameday = load_csv("sameday_by_regime.csv")
election = load_csv("election_window.csv", parse_dates=["Date"])
events = load_csv("event_comparison.csv")
episodes = load_csv("episode_returns.csv", index_col=0)
grid = load_csv("sensitivity_thresholds.csv")
trades = load_csv("ledger_s5_timed_hybrid.csv", parse_dates=["date"])

# ---------- header ----------
st.title("Volatility and the fear index: Nifty 50, India VIX and a VIX-timed put hedge")
st.markdown(
    "Financial Derivatives and Risk Management project, IIT Jodhpur · Subham Agrawal · "
    f"[Code on GitHub]({REPO_URL})  \n"
    f"Daily data {R['sample']['start']} to {R['sample']['end']} ({R['sample']['days']:,} trading days). "
    "Option prices are modelled with Black-Scholes-Merton using India VIX plus a skew, not traded prices."
)

p = perf.loc[PROPOSED]
u = perf.loc["Unhedged"]
c = st.columns(4)
c[0].metric("Volatility risk premium", f"{R['vrp']['mean_vrp']:.1f} vol pts",
            f"VIX above realised on {R['vrp']['share_positive']:.0%} of days", delta_color="off")
c[1].metric("Proposed hedge CAGR", f"{p.CAGR:.1f}%", f"{p.CAGR - u.CAGR:+.1f} pts vs unhedged")
c[2].metric("Proposed max drawdown", f"{p.maxDD:.0f}%", f"{p.maxDD - u.maxDD:+.0f} pts vs unhedged")
c[3].metric("Time holding puts", f"{p.share_time_hedged:.0f}%")

st.warning(
    "Honest caveat: almost all of the hedge's edge comes from one put held through the March 2020 crash. "
    f"From July 2020 it returned {R['ex_covid_performance'][PROPOSED]['CAGR']:.1f}% a year against "
    f"{R['ex_covid_performance']['Unhedged']['CAGR']:.1f}% unhedged, roughly the cost of insurance."
)

tab_bt, tab_vix, tab_vrp, tab_elec, tab_sens = st.tabs(
    ["Backtest", "Nifty and VIX regimes", "Volatility risk premium", "June 2024 election", "Sensitivity"]
)

# ---------- 1. backtest ----------
with tab_bt:
    st.markdown(
        "**The rule.** On the first trading day of each month, if India VIX closes below 13, buy a "
        "3-month Nifty put 5% below spot on the whole portfolio. Sell half the first day VIX closes at 22 "
        "or higher, and the rest once VIX falls 20% from its peak. Reinvest the proceeds in Nifty."
    )
    left, right = st.columns([1, 3])
    with left:
        start = st.radio("Start from", ["2 Jan 2020 (full sample)", "1 Jul 2020 (after the COVID crash)"])
        picked = st.multiselect(
            "Strategies", list(values.columns),
            default=["Unhedged", "Always 1M 95% put", PROPOSED],
        )
    v = values.loc["2020-07-01":] if start.startswith("1 Jul") else values
    v = v[picked] / v[picked].iloc[0]  # rebase so every line starts at 1
    dd = (v / v.cummax() - 1) * 100

    def line(df, title, fmt):
        long = df.reset_index().melt("date", var_name="Strategy", value_name="v")
        return alt.Chart(long).mark_line(strokeWidth=1.5).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("v:Q", title=title, scale=alt.Scale(zero=False)),
            color=alt.Color("Strategy:N", legend=alt.Legend(orient="bottom", columns=2, title=None)),
            tooltip=["date:T", "Strategy", alt.Tooltip("v:Q", format=fmt)],
        )

    with right:
        if picked:
            st.altair_chart(line(v, "Growth of 1", ".3f").properties(height=320), width="stretch")
            st.altair_chart(line(dd, "Drawdown (%)", ".1f").properties(height=180), width="stretch")
        else:
            st.info("Pick at least one strategy.")

    st.subheader("All seven strategies")
    if start.startswith("1 Jul"):
        table = pd.DataFrame(R["ex_covid_performance"]).T[["CAGR", "vol", "sharpe", "maxDD", "worst_day"]]
    else:
        table = perf[["CAGR", "vol", "sharpe", "maxDD", "worst_day", "net_hedge_cost_pa", "share_time_hedged"]]
    st.dataframe(table.round(2), width="stretch")
    st.caption("Percent per year except Sharpe. A negative net hedge cost means the options made money.")

    with st.expander("Returns in each stress episode (%)"):
        st.dataframe(episodes, width="stretch")
    with st.expander(f"Every trade of the proposed strategy ({trades.trade_id.nunique()} puts)"):
        st.dataframe(
            trades.assign(date=trades.date.dt.date)[["date", "trade_id", "action", "K", "price", "vix", "regime"]].round(2),
            width="stretch", hide_index=True,
        )

# ---------- 2. Nifty and VIX ----------
with tab_vix:
    st.markdown(
        "Regimes: **Low** VIX below 13, **Normal** 13 to 20, **High** above 20. "
        f"Daily Nifty returns and changes in log VIX move against each other (correlation "
        f"{R['regimes']['corr_ret_dlogvix']:.2f})."
    )
    m = market[["Date", "Close", "VIX", "regime"]]
    brush = alt.selection_interval(encodings=["x"])
    base = alt.Chart(m).encode(x=alt.X("Date:T", title=None))
    nifty = base.mark_line(color="#333", strokeWidth=1).encode(
        y=alt.Y("Close:Q", title="Nifty 50", scale=alt.Scale(zero=False)),
        tooltip=["Date:T", alt.Tooltip("Close:Q", format=",.0f"), alt.Tooltip("VIX:Q", format=".1f"), "regime"],
    ).properties(height=260).transform_filter(brush)
    vix = base.mark_circle(size=8).encode(
        y=alt.Y("VIX:Q", title="India VIX"),
        color=alt.Color("regime:N", sort=REGIME_ORDER, title="Regime",
                        scale=alt.Scale(domain=REGIME_ORDER, range=REGIME_COLOURS)),
        tooltip=["Date:T", alt.Tooltip("VIX:Q", format=".1f"), "regime"],
    ).properties(height=200).add_params(brush)
    st.altair_chart(alt.vconcat(nifty, vix).resolve_scale(color="independent"), width="stretch")
    st.caption("Drag across the VIX chart to zoom the Nifty chart into that window.")

    st.subheader("Same-day Nifty returns by regime")
    st.dataframe(sameday.set_index("regime").round(2), width="stretch")
    st.caption(
        f"Volatility is about {sameday.set_index('regime').ann_vol['Low']:.0f}% a year in Low and "
        f"{sameday.set_index('regime').ann_vol['High']:.0f}% in High, but average daily returns do not "
        f"differ significantly (Kruskal-Wallis p = {R['regimes']['kruskal_daily_p']:.2f})."
    )

# ---------- 3. VRP ----------
with tab_vrp:
    st.markdown(
        "The volatility risk premium is India VIX minus the volatility Nifty actually delivered over the "
        f"next 21 trading days. It averaged **{R['vrp']['mean_vrp']:.1f} vol points**, positive on "
        f"{R['vrp']['share_positive']:.0%} of days (Newey-West t = {R['vrp']['nw_t_mean_vrp']:.1f}): "
        "option buyers usually pay more than the volatility they get."
    )
    vr = market.dropna(subset=["rv21_fwd"])[["Date", "VIX", "rv21_fwd"]].rename(
        columns={"VIX": "India VIX", "rv21_fwd": "Realised vol, next 21 days"}
    )
    long = vr.melt("Date", var_name="Series", value_name="Vol")
    st.altair_chart(
        alt.Chart(long).mark_line(strokeWidth=1).encode(
            x=alt.X("Date:T", title=None), y=alt.Y("Vol:Q", title="Annualised vol (%)"),
            color=alt.Color("Series:N", legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Date:T", "Series", alt.Tooltip("Vol:Q", format=".1f")],
        ).properties(height=320).interactive(bind_y=False),
        width="stretch",
    )
    st.subheader("By regime")
    st.dataframe(vrp_regime.set_index("regime").round(2), width="stretch")

# ---------- 4. election ----------
with tab_elec:
    e = R["election"]
    st.markdown(
        f"Before the 4 June 2024 result, VIX rose from about {e['base_vix_q1_2024']:.0f} to the mid-20s. "
        f"On result day Nifty fell **{e['nifty_ret_4jun_pct']:.1f}%** (intraday low {e['intraday_low_4jun_pct']:.1f}%), "
        "close to the implied event move, and VIX fell 29% the next day as the uncertainty resolved."
    )
    el = election[["Date", "ret_pct", "VIX", "put22500"]].rename(
        columns={"ret_pct": "Nifty return (%)", "put22500": "22,500 put price (model)"}
    )
    st.dataframe(el.assign(Date=el.Date.dt.date).round(2), width="stretch", hide_index=True)
    st.image(str(FIG / "fig4_election_window.png"))
    st.subheader("Compared with other shock days")
    st.dataframe(events.round(2), width="stretch", hide_index=True)

# ---------- 5. sensitivity ----------
with tab_sens:
    st.markdown(
        "The thresholds (buy below 13, first sale at 22) were chosen on the same data, so here is every "
        "combination that was tested. The conclusion does not hinge on the exact values."
    )
    metric = st.radio("Colour by", ["CAGR", "maxDD", "sharpe", "calmar"], horizontal=True)
    heat = alt.Chart(grid).mark_rect().encode(
        x=alt.X("spike1:O", title="Sell first half when VIX closes at or above"),
        y=alt.Y("buy_below:O", title="Buy puts when VIX is below", sort="descending"),
        color=alt.Color(f"{metric}:Q", scale=alt.Scale(scheme="redyellowgreen")),
        tooltip=["buy_below", "spike1", "CAGR", "maxDD", "sharpe", "calmar"],
    ).properties(height=300)
    text = heat.mark_text(fontSize=13).encode(text=alt.Text(f"{metric}:Q", format=".2f"), color=alt.value("black"))
    st.altair_chart(heat + text, width="stretch")
    st.caption("The proposed rule is buy below 13, first sale at 22.")
    st.image(str(FIG / "fig8_sensitivity.png"))

st.divider()
st.caption(
    "Limitations: modelled option prices, VIX (a 30-day measure) used to price 3-month puts, one true crash "
    f"in six years, no taxes or brokerage. Full method in the [README]({REPO_URL})."
)

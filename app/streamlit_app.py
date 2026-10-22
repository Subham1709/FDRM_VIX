"""Nifty 50, India VIX and a VIX-timed put hedge: a read-only web app.

Every number and series here is read from files that fdrm_vix_analysis.py already
saved in output/. The app does not re-run the backtest; it only rebases the saved
equity curves when you pick a later start date. The one live calculation is the
insurance cost calculator on the Introduction tab, which uses the same
Black-Scholes pricing as the analysis.

Run locally from the repo root:  streamlit run app/streamlit_app.py
"""
import json
import math
from pathlib import Path
from statistics import NormalDist

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

# Plain-English names for the seven strategies (the technical names are in the files).
FRIENDLY = {
    "Unhedged": "No hedge (just hold Nifty)",
    "Always 1M 95% put": "1-month put every month",
    "Always 1M 95/85 put spread": "1-month put spread every month",
    "Always 3M 95% put, rolled monthly": "3-month put every month",
    "VIX-timed 3M put, hold": "Put only when VIX < 13, held to expiry",
    PROPOSED: "Put only when VIX < 13, sold in spikes (our rule)",
    "VIX-timed 3M put, sell all at VIX 22": "Put only when VIX < 13, all sold at VIX 22",
}
NO_HEDGE, OURS = FRIENDLY["Unhedged"], FRIENDLY[PROPOSED]
STRATEGY_COLOURS = {  # fixed colours so "no insurance" and "proposed" always look the same
    NO_HEDGE: "#222222", OURS: "#1f6fd1",
    FRIENDLY["Always 1M 95% put"]: "#e8772e", FRIENDLY["Always 1M 95/85 put spread"]: "#e8b02e",
    FRIENDLY["Always 3M 95% put, rolled monthly"]: "#c2185b",
    FRIENDLY["VIX-timed 3M put, hold"]: "#2e9e6b", FRIENDLY["VIX-timed 3M put, sell all at VIX 22"]: "#7b57c8",
}
METRIC_NAMES = {
    "CAGR": "Return a year (%)", "vol": "Volatility (%)", "sharpe": "Sharpe",
    "maxDD": "Worst fall (%)", "worst_day": "Worst day (%)",
    "net_hedge_cost_pa": "Insurance cost a year (%)", "share_time_hedged": "Time insured (%)",
}
TRADE_ACTIONS = {
    "open": "Bought the put", "roll_sell": "Swapped for a fresh 3-month put", "expiry": "Expired",
    "monetise_1": "Sold half (VIX reached 22)", "monetise_trail": "Sold the rest (VIX 20% off its peak)",
}

st.set_page_config(page_title="Group 8 · India VIX hedge", layout="wide")


@st.cache_data
def load_csv(name, **kw):
    return pd.read_csv(OUT / name, **kw)


@st.cache_data
def load_results():
    return json.loads((OUT / "results.json").read_text())


R = load_results()
perf = load_csv("backtest_performance.csv", index_col=0).rename(index=FRIENDLY)
values = load_csv("backtest_values.csv", parse_dates=["date"]).set_index("date").rename(columns=FRIENDLY)
market = load_csv("nifty_vix_merged.csv", parse_dates=["Date"])
vrp_regime = load_csv("vrp_by_regime.csv")
sameday = load_csv("sameday_by_regime.csv")
election = load_csv("election_window.csv", parse_dates=["Date"])
events = load_csv("event_comparison.csv")
episodes = load_csv("episode_returns.csv", index_col=0).rename(columns=FRIENDLY)
grid = load_csv("sensitivity_thresholds.csv")
trades = load_csv("ledger_s5_timed_hybrid.csv", parse_dates=["date"])

p, u = perf.loc[OURS], perf.loc[NO_HEDGE]
ex_covid = R["ex_covid_performance"]
first = trades[trades.trade_id == 0].set_index("action")
covid_multiple = first.loc["monetise_trail", "price"] / first.loc["open", "price"]


def put_price(spot, strike, years, vol, r=0.065, q=0.013):
    """Black-Scholes price of a European put (the same formula the analysis uses)."""
    n = NormalDist().cdf
    d1 = (math.log(spot / strike) + (r - q + vol ** 2 / 2) * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    return strike * math.exp(-r * years) * n(-d2) - spot * math.exp(-q * years) * n(-d1)


def hedge_put_cost_pct(vix):
    """Cost of the project's 3-month put, 5% below spot, as % of the portfolio."""
    spot, strike = 24000.0, 22800.0
    otm_pct = (1 - strike / spot) * 100
    vol = (vix + 0.6 * otm_pct + 0.5) / 100  # VIX + put skew + bid/ask, as in the analysis
    return put_price(spot, strike, 91 / 365, vol) / spot * 100


# ---------- header ----------
st.title("Nifty 50, India VIX and a crash-insurance rule")
st.markdown(
    "FDRM course project, **Group 8**, IIT Jodhpur · "
    f"[Code and report on GitHub]({REPO_URL})  \n"
    f"Daily data from {R['sample']['start']} to {R['sample']['end']} ({R['sample']['days']:,} trading days). "
    "If you are new to options, read the Introduction tab first."
)

c = st.columns(4)
c[0].metric("Return per year, our rule", f"{p.CAGR:.1f}%",
            f"{p.CAGR - u.CAGR:+.1f} pts vs no hedge", help="CAGR: compound annual growth rate")
c[1].metric("Worst fall, our rule", f"{p.maxDD:.0f}%", f"{p.maxDD - u.maxDD:+.0f} pts vs no hedge",
            help="Maximum drawdown: the biggest drop from a previous high")
c[2].metric("Days holding a put", f"{p.share_time_hedged:.0f}%")
c[3].metric("Average VIX overpricing", f"{R['vrp']['mean_vrp']:.1f} pts",
            f"on {R['vrp']['share_positive']:.0%} of days", delta_color="off",
            help="Volatility risk premium: India VIX minus the volatility that actually followed")

tab_start, tab_bt, tab_vix, tab_vrp, tab_elec, tab_sens = st.tabs([
    "Introduction", "Did the hedge work?", "India VIX", "Is insurance overpriced?",
    "2024 election", "Robustness check",
])

# ---------- 0. introduction ----------
with tab_start:
    st.subheader("What the project is about")
    st.markdown(
        "Suppose your money is invested in the **Nifty 50** (the 50 largest companies on the NSE). It goes up "
        f"over time, but it can also crash: in early 2020 it fell {abs(u.maxDD):.0f}% in about two months. "
        "You can protect yourself with a **put option**, which works like insurance: you pay a small premium, "
        "and if the market falls far enough the put pays you back.\n\n"
        "The problem is that this insurance is expensive when everyone wants it. So our question was: "
        "**can we buy puts when they are cheap and sell them when people panic?** We used **India VIX** "
        "to decide when."
    )

    st.subheader("Basic terms")
    st.markdown(
        "**Volatility** is how much prices move. A calm market moves about 0.5% a day; in a panic Nifty can move "
        "5% or more in a day. It is usually quoted per year: about 9% in calm periods here, over 30% in a panic.\n\n"
        "**India VIX** is published by NSE every day and is calculated from Nifty option prices. It is the "
        "market's estimate of how much Nifty will move over the next 30 days, which is why it is called the "
        "fear index. We split it into three regimes: below 13 is calm, 13 to 20 is normal, above 20 is "
        "nervous. It peaked at 83.6 on 24 March 2020. A rough rule: VIX ÷ 3.5 is the expected move in a month, "
        "so VIX 14 means about ±4%.\n\n"
        "**A put option** gives you the right to sell Nifty at a fixed level (the **strike**) on a fixed date. "
        "If Nifty ends below the strike, the put pays the difference. We use a 3-month put with the strike 5% "
        "below the current level, so it works like insurance with a 5% deductible.\n\n"
        "**Options are usually overpriced.** On most days VIX was higher than the volatility that actually "
        f"followed: by {R['vrp']['mean_vrp']:.1f} points on average, on {R['vrp']['share_positive']:.0%} of days. "
        "This gap is the **volatility risk premium**. Option sellers earn it, the same way insurance companies "
        "do, so buying protection all the time costs a lot."
    )

    st.subheader("Our rule")
    st.markdown(
        "1. On the first trading day of each month, buy the put only if VIX is **below 13** (cheap).\n"
        "2. If VIX closes at **22 or higher**, sell half the put while it is expensive.\n"
        "3. Sell the rest once VIX has fallen 20% from its peak, and put the money back into Nifty.\n\n"
        "In short: buy umbrellas when it is sunny and sell them when it rains."
    )

    st.subheader("Insurance cost calculator")
    st.caption("A 3-month put, strike 5% below today's Nifty, covering the whole portfolio.")
    left, right = st.columns([1, 2])
    with left:
        vix_now = st.slider("India VIX when you buy", 9, 60, 12)
        fall = st.slider("Nifty fall over the 3 months (%)", 0, 40, 20)
    cost = hedge_put_cost_pct(vix_now)
    payout = max(fall - 5.0, 0.0)  # the put pays everything beyond the 5% deductible
    with right:
        m = st.columns(3)
        m[0].metric("Cost of the put", f"{cost:.2f}%")
        m[1].metric("Payout at expiry", f"{payout:.1f}%")
        m[2].metric("Loss with the put", f"{-fall + payout - cost:.1f}%",
                    f"vs {-fall:.0f}% without", delta_color="off")
        st.markdown(
            f"All values are % of the portfolio. The same put costs {hedge_put_cost_pct(12):.1f}% at VIX 12 and "
            f"{hedge_put_cost_pct(25):.1f}% at VIX 25, about "
            f"{hedge_put_cost_pct(25) / hedge_put_cost_pct(12):.1f} times more. That is why the rule only buys "
            "when VIX is low."
        )
    st.caption("Priced with Black-Scholes at VIX plus a skew and bid/ask margin, the same way as in the analysis.")

    st.subheader("Main results")
    st.markdown(
        f"- Buying puts only when VIX was low gave {p.CAGR:.1f}% a year against {u.CAGR:.1f}% with no hedge, "
        f"and the worst fall was {abs(p.maxDD):.0f}% instead of {abs(u.maxDD):.0f}%.\n"
        "- Buying a put every month cost 3% to 5% of the portfolio a year and ended below the unhedged return.\n"
        f"- One caveat: most of the gain came from a single put bought in January 2020 for "
        f"{-first.loc['open', 'cash'] * 100:.1f}% of the portfolio and sold in the COVID crash for "
        f"{covid_multiple:.0f} times its price. From July 2020 the rule returned {ex_covid[PROPOSED]['CAGR']:.1f}% "
        f"a year against {ex_covid['Unhedged']['CAGR']:.1f}% with no hedge, so in normal years the protection "
        "costs about 0.5% a year. It is insurance, not a way to beat the market."
    )

    with st.expander("Glossary"):
        st.markdown(
            "- **Nifty 50:** index of the 50 largest companies on India's National Stock Exchange (NSE).\n"
            "- **Volatility:** how much prices move, per year, in %.\n"
            "- **India VIX:** the market's forecast of Nifty's volatility over the next 30 days, from option prices.\n"
            "- **Option:** a contract giving the right, not the obligation, to sell (a put) or buy (a call) at a set price.\n"
            "- **Strike:** the level below which the put starts paying.\n"
            "- **Premium:** the price you pay for an option.\n"
            "- **Hedge:** holding protection alongside an investment.\n"
            "- **Volatility risk premium:** how much more options charge than the volatility that follows.\n"
            "- **Drawdown:** a fall from the previous high. Maximum drawdown is the worst one.\n"
            "- **CAGR:** average growth per year, compounded.\n"
            "- **Sharpe ratio:** return above a safe rate (6.5% here) per unit of volatility. Higher is better.\n"
            "- **Backtest:** replaying history day by day as if you had followed the rule."
        )

# ---------- 1. backtest ----------
with tab_bt:
    st.markdown(
        "Each line shows how ₹1 invested on 2 January 2020 grew under each strategy. The lower chart shows how "
        "far each one was below its previous high, so a shallower dip means better protection."
    )
    left, right = st.columns([1, 3])
    with left:
        start = st.radio("Start from", ["2 Jan 2020 (full sample)", "1 Jul 2020 (after the COVID crash)"])
    with right:
        picked = st.multiselect(
            "Strategies to compare", list(values.columns),
            default=[NO_HEDGE, FRIENDLY["Always 1M 95% put"], OURS],
        )
    v = values.loc["2020-07-01":] if start.startswith("1 Jul") else values
    v = v[picked] / v[picked].iloc[0]  # rebase so every line starts at 1
    dd = (v / v.cummax() - 1) * 100

    def line(df, title, fmt, legend=True):
        long = df.reset_index().melt("date", var_name="Strategy", value_name="v")
        colours = alt.Scale(domain=picked, range=[STRATEGY_COLOURS[n] for n in picked])
        return alt.Chart(long).mark_line(strokeWidth=1.5).encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("v:Q", title=title, scale=alt.Scale(zero=False)),
            color=alt.Color("Strategy:N", scale=colours,
                            legend=alt.Legend(orient="top", columns=2, title=None, labelLimit=400) if legend else None),
            tooltip=["date:T", "Strategy", alt.Tooltip("v:Q", format=fmt)],
        )

    if picked:
        st.altair_chart(line(v, "Value of ₹1 invested", ".3f").properties(height=340), width="stretch")
        st.altair_chart(line(dd, "Below previous high (%)", ".1f", legend=False).properties(height=190),
                        width="stretch")
    else:
        st.info("Pick at least one strategy.")

    st.subheader("All seven strategies")
    if start.startswith("1 Jul"):
        table = pd.DataFrame(ex_covid).T.rename(index=FRIENDLY)[["CAGR", "vol", "sharpe", "maxDD", "worst_day"]]
    else:
        table = perf[["CAGR", "vol", "sharpe", "maxDD", "worst_day", "net_hedge_cost_pa", "share_time_hedged"]]
    st.dataframe(table.round(2).rename(columns=METRIC_NAMES), width="stretch")
    st.caption("A negative insurance cost means the options earned more than they cost.")

    with st.expander("Returns in each stress episode (%)"):
        st.dataframe(episodes, width="stretch")
    with st.expander(f"Every trade of the proposed rule ({trades.trade_id.nunique()} puts bought)"):
        st.dataframe(
            trades.assign(date=trades.date.dt.date, action=trades.action.map(TRADE_ACTIONS))
            [["date", "trade_id", "action", "K", "price", "vix", "regime"]].round(2)
            .rename(columns={"date": "Date", "trade_id": "Put no.", "action": "What happened", "K": "Strike",
                             "price": "Price (index points)", "vix": "VIX", "regime": "Regime"}),
            width="stretch", hide_index=True,
        )
    with st.expander("Technical names of the strategies"):
        st.dataframe(pd.Series(FRIENDLY, name="Name in this app").rename_axis("Name in the report"),
                     width="stretch")

# ---------- 2. Nifty and VIX ----------
with tab_vix:
    st.markdown(
        "Top: Nifty 50. Bottom: India VIX, coloured by regime (blue below 13, grey 13 to 20, red above 20). "
        "VIX jumps when Nifty falls."
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

    st.subheader("How Nifty behaves in each regime")
    sd = sameday.set_index("regime")
    st.dataframe(
        sd.round(2).rename(columns={"mean_pct": "Average day (%)", "sd_pct": "Typical daily move (%)",
                                    "ann_vol": "Volatility per year (%)", "worst_pct": "Worst day (%)",
                                    "days": "Number of days"}),
        width="stretch",
    )
    st.caption(
        f"Nifty moves about {sd.ann_vol['High'] / sd.ann_vol['Low']:.0f} times as much when VIX is high "
        f"({sd.ann_vol['High']:.0f}% a year against {sd.ann_vol['Low']:.0f}%), but the average daily return "
        f"is not significantly different (Kruskal-Wallis p = {R['regimes']['kruskal_daily_p']:.2f}). "
        "VIX tells you how big the moves will be, not which direction."
    )

# ---------- 3. VRP ----------
with tab_vrp:
    st.markdown(
        "Blue is India VIX, the volatility the market expected. Orange is the volatility Nifty actually had over "
        "the next 21 trading days. Blue is above orange most of the time, so option buyers usually paid for more "
        "movement than they got. The exceptions are crashes, where orange goes above blue."
    )
    vr = market.dropna(subset=["rv21_fwd"])[["Date", "VIX", "rv21_fwd"]].rename(
        columns={"VIX": "India VIX (expected)", "rv21_fwd": "What actually happened next month"}
    )
    long = vr.melt("Date", var_name="Series", value_name="Vol")
    st.altair_chart(
        alt.Chart(long).mark_line(strokeWidth=1).encode(
            x=alt.X("Date:T", title=None), y=alt.Y("Vol:Q", title="Volatility per year (%)"),
            color=alt.Color("Series:N", legend=alt.Legend(orient="bottom", title=None, labelLimit=400),
                            scale=alt.Scale(domain=list(vr.columns[1:]), range=["#1f6fd1", "#e8772e"])),
            tooltip=["Date:T", "Series", alt.Tooltip("Vol:Q", format=".1f")],
        ).properties(height=320).interactive(bind_y=False),
        width="stretch",
    )
    st.markdown(
        f"On average VIX was **{R['vrp']['mean_vrp']:.1f} points** too high, on "
        f"{R['vrp']['share_positive']:.0%} of days (Newey-West t = {R['vrp']['nw_t_mean_vrp']:.1f}, so this is "
        "not luck). This gap is called the **volatility risk premium**."
    )
    st.subheader("By regime")
    st.dataframe(
        vrp_regime.assign(VRP_pos=vrp_regime.VRP_pos * 100).set_index("regime").round(2).rename(columns={
            "VIX": "Average VIX", "RV_fwd": "Actual volatility next month", "VRP": "Overpricing (points)",
            "VRP_pos": "Days overpriced (%)", "days": "Number of days"}),
        width="stretch",
    )
    st.caption("Overpricing is largest right after a shock (the High regime): the worst time to buy insurance.")

# ---------- 4. election ----------
with tab_elec:
    e = R["election"]
    st.markdown(
        "The 2024 Lok Sabha result had a known date but an uncertain outcome, so VIX rose in the weeks before it, "
        f"from about {e['vix_min_apr_2024']:.0f} in April to the mid-20s. On result day (4 June) Nifty fell "
        f"{abs(e['nifty_ret_4jun_pct']):.1f}%, and the next day VIX dropped {abs(e['vix_change_5jun_pct']):.0f}% "
        "once the result was known. Puts were cheap in April and expensive by late May."
    )
    el = election[["Date", "Close", "ret_pct", "VIX", "put22500"]].rename(
        columns={"Close": "Nifty", "ret_pct": "Nifty change (%)", "VIX": "India VIX",
                 "put22500": "Price of a 22,500 put (points, modelled)"}
    )
    st.dataframe(el.assign(Date=el.Date.dt.date).round(2), width="stretch", hide_index=True)
    st.image(str(FIG / "fig4_election_window.png"))
    st.subheader("Compared with other shock days")
    st.dataframe(
        events.fillna("").round(2).rename(columns={
            "event": "Event", "date": "Date", "nifty_ret_pct": "Nifty change (%)", "vix_prev": "VIX day before",
            "vix": "VIX on the day", "vix_chg_pct": "VIX change (%)",
            "straddle_prev_pct": "Big-move bet, day before (%)", "straddle_pct": "Big-move bet, on the day (%)",
            "move_vs_implied": "Move ÷ expected move"}),
        width="stretch", hide_index=True,
    )
    st.caption("A big-move bet (a \"straddle\": one call plus one put) pays if Nifty moves a lot either way, so its "
               "price, as % of Nifty, shows how big a move the market expects over the next month. "
               "\"Move ÷ expected move\" above 1 means the day was a bigger shock than VIX had priced for a single day.")

# ---------- 5. sensitivity ----------
with tab_sens:
    st.markdown(
        "We picked the levels 13 and 22 using the same data we tested on, which can flatter the result. This "
        "grid repeats the backtest for other buy and sell levels. Every \"buy only below X\" row beats the "
        "\"always\" row (buying every month), so the result does not depend on 13 and 22 exactly."
    )
    metric_labels = {"CAGR": "Return per year (%)", "maxDD": "Worst fall (%)",
                     "sharpe": "Sharpe ratio", "calmar": "Calmar ratio (return ÷ worst fall)"}
    picked_label = st.radio("Colour by", list(metric_labels.values()), horizontal=True)
    metric = {v: k for k, v in metric_labels.items()}[picked_label]
    heat = alt.Chart(grid).mark_rect().encode(
        x=alt.X("spike1:O", title="Sell the first half when VIX reaches"),
        y=alt.Y("buy_below:O", title="Buy puts only when VIX is below", sort="descending"),
        color=alt.Color(f"{metric}:Q", title=picked_label, scale=alt.Scale(scheme="redyellowgreen")),
        tooltip=["buy_below", "spike1", "CAGR", "maxDD", "sharpe", "calmar"],
    ).properties(height=300)
    text = heat.mark_text(fontSize=13).encode(text=alt.Text(f"{metric}:Q", format=".2f"), color=alt.value("black"))
    st.altair_chart(heat + text, width="stretch")
    st.caption("Our rule: buy below 13, first sale at 22. The \"always\" row buys every month regardless of VIX.")
    st.image(str(FIG / "fig8_sensitivity.png"))

st.divider()
st.caption(
    "Group 8, Financial Derivatives and Risk Management, IIT Jodhpur. "
    "Limitations: option prices are modelled from VIX rather than taken from real trades; VIX (a 30-day measure) "
    "is used to price 3-month puts; six years contain only one real crash; no taxes or brokerage. "
    f"Full method in the [README]({REPO_URL})."
)

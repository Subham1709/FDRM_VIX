"""Build docs/fdrm_vix_results.xlsx from the CSVs in output/ (run after fdrm_vix_analysis.py)."""
import json
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
XLSX = ROOT / "docs" / "fdrm_vix_results.xlsx"
R = json.loads((OUT / "results.json").read_text())
PROPOSED = "VIX-timed 3M put + hybrid monetisation (proposed)"
STRATS = ["Unhedged", "Always 1M 95% put", "Always 1M 95/85 put spread", "Always 3M 95% put, rolled monthly",
          "VIX-timed 3M put, hold", PROPOSED, "VIX-timed 3M put, sell all at VIX 22"]
LEDGERS = ["s1_always_put", "s2_always_spread", "s3_timed_hold", "s4_timed_hold", "s5_timed_hybrid", "s6_timed_all"]


def csv(name, **kw):
    return pd.read_csv(OUT / f"{name}.csv", **kw)


perf = csv("backtest_performance", index_col=0).rename_axis("Strategy").reset_index().rename(columns={
    "final": "Value of Rs 1 at end", "CAGR": "Return per year (%)", "vol": "Volatility (%)", "sharpe": "Sharpe",
    "sortino": "Sortino", "maxDD": "Max drawdown (%)", "calmar": "Calmar", "worst_day": "Worst day (%)",
    "worst_21d": "Worst 21 days (%)", "premium_paid_pa": "Premium paid (% a year)",
    "recovered_pa": "Recovered (% a year)", "net_hedge_cost_pa": "Net hedge cost (% a year)",
    "share_time_hedged": "Time hedged (%)"})

ex = pd.DataFrame(R["ex_covid_performance"]).T.rename_axis("Strategy").reset_index()[
    ["Strategy", "CAGR", "vol", "sharpe", "maxDD", "calmar"]].rename(columns={
        "CAGR": "Return per year (%)", "vol": "Volatility (%)", "sharpe": "Sharpe", "maxDD": "Max drawdown (%)",
        "calmar": "Calmar"})

daily = csv("nifty_vix_merged", parse_dates=["Date"])
daily = daily[["Date", "Open", "High", "Low", "Close", "ret", "VIX", "dvix", "rv21_trail", "rv21_fwd", "regime"]]
daily["VRP"] = daily["VIX"] - daily["rv21_fwd"]
daily = daily.rename(columns={
    "Close": "Nifty close", "Open": "Nifty open", "High": "Nifty high", "Low": "Nifty low",
    "ret": "Nifty log return", "VIX": "India VIX close", "dvix": "VIX log change",
    "rv21_trail": "Realised vol, past 21 days (%)", "rv21_fwd": "Realised vol, next 21 days (%)",
    "regime": "VIX regime", "VRP": "VRP: VIX minus next-21-day realised vol"})

values = csv("backtest_values", parse_dates=["date"]).rename(columns={"date": "Date"})

ledgers = []
for name, slug in zip(STRATS[1:], LEDGERS):
    led = csv(f"ledger_{slug}", parse_dates=["date"])
    led.insert(0, "Strategy", name)
    ledgers.append(led)
ledgers = pd.concat(ledgers).rename(columns={
    "date": "Date", "trade_id": "Trade id", "action": "Action", "K": "Strike", "qty": "Quantity (per Rs 1)",
    "price": "Option price (points)", "cash": "Cash flow (per Rs 1)", "vix": "India VIX",
    "regime": "Regime on the day", "open_regime": "Regime when opened"})

key = [
    ("Trading days", R["sample"]["days"]),
    ("Backtest", f"{R['backtest_period']['start']} to {R['backtest_period']['end']} "
                 f"({R['backtest_period']['years']} years)"),
    ("Average VRP (VIX minus realised vol, points)", round(R["vrp"]["mean_vrp"], 2)),
    ("Days with positive VRP", f"{R['vrp']['share_positive']:.0%}"),
    ("Newey-West t-stat of VRP", round(R["vrp"]["nw_t_mean_vrp"], 2)),
]
p = perf.set_index("Strategy")
for label, s in [("Our rule", PROPOSED), ("No hedge", "Unhedged")]:
    key += [(f"{label}: return per year (%)", round(p.loc[s, "Return per year (%)"], 2)),
            (f"{label}: max drawdown (%)", round(p.loc[s, "Max drawdown (%)"], 2)),
            (f"{label}: Sharpe", round(p.loc[s, "Sharpe"], 3)),
            (f"{label}: Rs 10 lakh grows to (Rs lakh)", round(10 * p.loc[s, "Value of Rs 1 at end"], 1))]

contents = [
    ("Performance", "All seven strategies, full backtest (2 Jan 2020 to 13 Apr 2026)"),
    ("Performance ex-COVID", "Same strategies from 1 Jul 2020"),
    ("Daily data", "Nifty 50 and India VIX by day, realised volatility, VRP and regime"),
    ("Backtest values", "Value of Rs 1 in each strategy, every trading day"),
    ("Trade ledgers", "Every option trade for the six hedged strategies"),
    ("VRP by regime", "Implied vs realised volatility by VIX regime"),
    ("Returns by regime", "Forward Nifty returns after each VIX regime"),
    ("Same-day by regime", "Same-day Nifty moves in each regime"),
    ("Election 2024", "Nifty, VIX and a modelled 22,500 put around 4 June 2024"),
    ("Shock days", "The election compared with other shock days"),
    ("Episodes", "Strategy returns in each stress episode"),
    ("Excess by regime", "Excess return vs no hedge, by regime (annualised and cumulative)"),
    ("Hedge cost by regime", "Premium paid and received by regime"),
    ("Sens. thresholds", "Buy level and first-sale level grid"),
    ("Sens. pricing", "Skew and bid/ask spread assumptions"),
    ("Sens. tenor", "Put length and selling rule"),
]

sheets = {
    "Performance": perf, "Performance ex-COVID": ex, "Daily data": daily, "Backtest values": values,
    "Trade ledgers": ledgers, "VRP by regime": csv("vrp_by_regime"), "Returns by regime": csv("returns_by_regime"),
    "Same-day by regime": csv("sameday_by_regime"), "Election 2024": csv("election_window"),
    "Shock days": csv("event_comparison"),
    "Episodes": csv("episode_returns").rename(columns={"Unnamed: 0": "Episode"}),
}
exc_a = csv("excess_return_by_regime_annualised").assign(Basis="Annualised (%)")
exc_c = csv("excess_return_by_regime_cumulative").assign(Basis="Cumulative (%)")
sheets["Excess by regime"] = pd.concat([exc_a, exc_c])
sheets["Hedge cost by regime"] = csv("hedge_cost_payoff_by_regime")
sheets["Sens. thresholds"] = csv("sensitivity_thresholds")
sheets["Sens. pricing"] = csv("sensitivity_pricing")
sheets["Sens. tenor"] = csv("sensitivity_rule_by_tenor")

with pd.ExcelWriter(XLSX, engine="openpyxl") as xw:
    pd.DataFrame().to_excel(xw, sheet_name="About")
    for name, df in sheets.items():
        df.to_excel(xw, sheet_name=name, index=False)

wb = load_workbook(XLSX)
head_fill = PatternFill("solid", fgColor="1F3864")
for ws in wb.worksheets[1:]:
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "B2"
    for i, col in enumerate(ws.iter_cols(min_row=1, max_row=min(ws.max_row, 200)), 1):
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col[1:]) if len(col) > 1 else 8
        ws.column_dimensions[get_column_letter(i)].width = min(max(width, len(str(col[0].value)) * 0.6, 10), 45)
        for c in col[1:]:
            if isinstance(c.value, float):
                c.number_format = "0.00E+00" if 0 < abs(c.value) < 0.01 else "0.000"
            elif hasattr(c.value, "year"):
                c.number_format = "yyyy-mm-dd"

ws = wb["About"]
ws.column_dimensions["A"].width = 46
ws.column_dimensions["B"].width = 80
rows = [("Volatility dynamics and the fear index: results workbook", None),
        ("FDRM course project, Group 8, IIT Jodhpur", None), (None, None),
        ("Code and report", "https://github.com/Subham1709/FDRM_VIX"),
        ("Live app", "https://subham-fdrm-vix.streamlit.app"),
        ("Note", "Option prices are modelled with Black-Scholes-Merton from India VIX (skew +0.6 vol pt per 1% OTM, "
                 "0.5 vol pt half-spread, r 6.5%, q 1.3%); payoffs at expiry use actual Nifty closes."),
        (None, None), ("Key results", None)] + key + [(None, None), ("Sheets", None)] + contents
for r, (a, b) in enumerate(rows, 1):
    ws.cell(r, 1, a)
    ws.cell(r, 2, b)
    ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
ws["A1"].font = Font(bold=True, size=14)
for r, (a, _) in enumerate(rows, 1):
    if a in ("Key results", "Sheets"):
        ws.cell(r, 1).font = Font(bold=True, size=12)
for r in range(1, ws.max_row + 1):
    v = ws.cell(r, 2).value
    if isinstance(v, str) and v.startswith("https://"):
        ws.cell(r, 2).hyperlink = v
        ws.cell(r, 2).font = Font(color="0563C1", underline="single")
wb.save(XLSX)
print(XLSX, [s.title for s in wb.worksheets])

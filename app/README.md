# Web app

A small read-only website for this project, built with [Streamlit](https://streamlit.io).
It does not re-run the analysis: it reads the tables and figures the analysis already saved and draws them as interactive charts. The only live calculation is the insurance cost calculator on the Introduction tab.

## What `streamlit_app.py` does, in plain English

1. **Loads saved results.** Each `load_...` function reads one saved file. `@st.cache_data` means the file is read once when the server starts, not on every click.
2. **Plain names.** `FRIENDLY` renames the seven strategies (for example "Unhedged" becomes "No hedge (just hold Nifty)"), and table columns get everyday names. The technical names are listed in an expander on the backtest tab.
3. **Header and metric cards.** The headline numbers are read from the result files, so they always match the report.
4. **Introduction tab.** Explains Nifty, volatility, India VIX, put options and the rule from scratch, for an audience without a finance background. Its calculator prices the project's 3-month put (strike 5% below spot) with the same Black-Scholes formula and assumptions as the analysis, for any VIX level, and shows what it pays back if Nifty falls by a chosen amount.
5. **The other tabs.** Each opens with a short explanation of what the chart shows. Charts use Altair (hover for exact values); tables use `st.dataframe` (sortable).
6. **Widgets.** Radio buttons, sliders and dropdowns only change what is *shown*. Every time you click, Streamlit re-runs the script top to bottom with the new widget values; that is the whole programming model.
7. **Backtest tab.** Reads `output/backtest_values.csv` (daily value of each strategy). Picking "1 Jul 2020" divides each line by its value on that day so all lines start at 1, and the drawdown is value ÷ running peak − 1.
8. **Sensitivity tab.** A heatmap of `output/sensitivity_thresholds.csv`: every buy/sell VIX threshold pair the script tested.

## Run it on your laptop

```bash
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```

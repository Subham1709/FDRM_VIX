# Web app

A small read-only website for this project, built with [Streamlit](https://streamlit.io).
It does not re-run the analysis: it reads the tables, figures and model the analysis already saved, and draws them as interactive charts.

## What `streamlit_app.py` does, in plain English

1. **Loads saved results.** Each `load_...` function reads one saved file. `@st.cache_data` means the file is read once when the server starts, not on every click.
2. **Header and metric cards.** The headline numbers are read from the result files, so they always match the report.
3. **Tabs.** Each `with tab_...:` block is one tab. Charts use Altair (hover for exact values); tables use `st.dataframe` (sortable).
4. **Widgets.** Radio buttons, checkboxes, sliders and dropdowns only change what is *shown*. Every time you click, Streamlit re-runs the script top to bottom with the new widget values; that is the whole programming model.
5. **Backtest tab.** Reads `output/backtest_values.csv` (daily value of each strategy). Picking "1 Jul 2020" divides each line by its value on that day so all lines start at 1, and the drawdown is value ÷ running peak − 1. That is the only arithmetic the app does.
6. **Sensitivity tab.** A heatmap of `output/sensitivity_thresholds.csv`: every buy/sell VIX threshold pair the script tested.

## Run it on your laptop

```bash
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```

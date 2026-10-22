// Builds the FDRM presentation from the charts in ./figures.
// Run: npm install && node build_deck.js [out.pptx]
// Optional: APPLY_THEME=<path to an applyTheme helper> writes THEME's fonts and colours into the file;
// without it the deck still builds, with PowerPoint's default theme colours.
const path = require("path");
const pptxgen = require("pptxgenjs");
const applyTheme = process.env.APPLY_THEME ? require(process.env.APPLY_THEME).applyTheme : null;

const FIG = path.join(__dirname, "figures");
const OUT = process.argv[2] || "fdrm_vix_presentation.pptx";

const THEME = {
  name: "Fear Index",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0F1B2D", lt1: "FFFFFF", dk2: "1B2A41", lt2: "EEF2F7",
    accent1: "E8772E", accent2: "2A78D6", accent3: "8A94A6", accent4: "EDA100",
    accent5: "E87BA4", accent6: "1BAF7A", hlink: "2A78D6", folHlink: "4A3AA7",
  },
};
const HEX = THEME.colors;
const ORANGE_TINT = "FCE9DC"; // fear-side card tint (hex-only spots)
const BLUE_TINT = "E3EEFB";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Nifty Options, India VIX and a VIX-Timed Hedge";
pres.subject = "FDRM course project: volatility dynamics and the fear index";
const C = pres.SchemeColor;

const W = 13.333, M = 0.6, CW = W - 2 * M;

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 2.0, w: CW, h: 1.9, fontSize: 44, bold: true, color: C.background1, valign: "bottom", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: M, y: 4.15, w: CW, h: 1.6, fontSize: 20, color: C.background2, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: HEX.lt1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.3, w: CW, h: 1.0, fontSize: 34, bold: true, color: C.text2, valign: "middle", align: "left" }, text: "" } },
    { text: { text: "FDRM  ·  Nifty options and India VIX", options: { x: M, y: 7.0, w: 6, h: 0.3, fontSize: 10, color: C.accent3, margin: 0 } } },
  ],
  slideNumber: { x: W - M - 0.6, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: C.accent3, align: "right", margin: 0 },
});
pres.defineSlideMaster({
  title: "CLOSING_DARK",
  background: { color: HEX.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: M, y: 0.5, w: CW, h: 1.2, fontSize: 38, bold: true, color: C.background1, valign: "middle", align: "left" }, text: "" } },
  ],
  slideNumber: { x: W - M - 0.6, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: C.background2, align: "right", margin: 0 },
});

// ---------- helpers ----------
function card(slide, x, y, w, h, fill, name) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill || C.background2 }, line: { type: "none" }, objectName: name || "card" });
}
function numCircle(slide, x, y, d, label, fill) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" }, objectName: `marker ${label}` });
  slide.addText(String(label), { x, y, w: d, h: d, align: "center", valign: "middle", fontSize: 16, bold: true, color: C.background1, margin: 0, isTextBox: true });
}
function headDesc(slide, x, y, w, h, head, desc, opts = {}) {
  slide.addText([
    { text: head, options: { bold: true, fontSize: opts.headSize || 16, color: opts.headColor || C.text2, breakLine: true, paraSpaceAfter: 4 } },
    { text: desc, options: { fontSize: opts.descSize || 14, color: opts.descColor || C.text1 } },
  ], { x, y, w, h, valign: "top", margin: 0, isTextBox: true, objectName: opts.name || head });
}
function stat(slide, x, y, w, h, big, label, color, opts = {}) {
  card(slide, x, y, w, h, opts.fill, `stat ${big}`);
  slide.addText(big, { x: x + 0.25, y: y + 0.18, w: w - 0.5, h: opts.bigH || 0.8, fontSize: opts.bigSize || 36, bold: true, color, margin: 0, valign: "middle", isTextBox: true, objectName: `stat value ${big}` });
  slide.addText(label, { x: x + 0.25, y: y + 0.22 + (opts.bigH || 0.8), w: w - 0.5, h: h - 0.32 - (opts.bigH || 0.8), fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: `stat label ${big}` });
}
function bullets(items, size = 14, color) {
  return items.map((t, i) => ({ text: t, options: { bullet: true, fontSize: size, color: color || C.text1, paraSpaceAfter: 8, breakLine: i < items.length - 1 } }));
}
function img(slide, file, x, y, w, ratio, alt) {
  slide.addImage({ path: path.join(FIG, file), x, y, w, h: w * ratio, altText: alt, objectName: alt });
}
const chartText = {
  titleFontFace: "+mn-lt", titleFontSize: 14, titleColor: HEX.dk2,
  catAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 12, catAxisLabelColor: HEX.dk2,
  valAxisLabelFontFace: "+mn-lt", valAxisLabelFontSize: 12, valAxisLabelColor: HEX.dk2,
  dataLabelFontFace: "+mn-lt", dataLabelFontSize: 12, dataLabelColor: HEX.dk2,
  legendFontFace: "+mn-lt", legendFontSize: 12, legendColor: HEX.dk2,
};
function barChart(slide, labels, values, colors, o) {
  slide.addChart(pres.charts.BAR, [{ name: o.series || "Value", labels, values }], Object.assign({
    x: o.x, y: o.y, w: o.w, h: o.h, barDir: o.dir || "col", barGapWidthPct: 60,
    showTitle: true, title: o.title, chartColors: colors,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: o.fmt || "0.0",
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
    catAxisLineShow: true, catAxisLineColor: HEX.accent3, showLegend: false,
    valAxisMinVal: o.min, valAxisMaxVal: o.max, catAxisOrientation: o.dir === "bar" ? "maxMin" : "minMax",
    objectName: o.title,
  }, chartText));
}
const tableStyle = { fontSize: 14, color: C.text1, border: { type: "solid", pt: 0.5, color: C.accent3 }, valign: "middle", margin: [0.04, 0.08, 0.04, 0.08] };
function tableRows(header, rows, boldCol) {
  const head = header.map(h => ({ text: h, options: { bold: true, color: C.background1, fill: { color: C.text2 } } }));
  const body = rows.map((r, i) => r.map((c, j) => ({ text: c, options: { fill: { color: i % 2 ? C.background2 : C.background1 }, bold: j === 0 || j === boldCol } })));
  return [head, ...body];
}

let s;
// ================= 1. Title =================
pres.addSection({ title: "Overview" });
s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Overview" });
s.addText("Nifty Options, India VIX and a VIX-Timed Hedge", { placeholder: "title" });
s.addText("Volatility dynamics, the 4 June 2024 election, and a backtest of protection bought in calm markets and sold into fear\nFDRM course project  ·  Group 8, IIT Jodhpur", { placeholder: "body" });
s.addNotes("This deck covers the three syllabus topics: implied versus realised volatility and the volatility risk premium, how India VIX is built and used as a sentiment gauge, and how VIX regimes relate to Nifty returns. It then looks at option premiums around the 4 June 2024 election result and proposes and backtests a protection strategy for a long-term Nifty portfolio.");

// ================= 2. Four numbers =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Overview" });
s.addText("Four numbers that sum up the study", { placeholder: "title" });
{
  const cw = (CW - 3 * 0.3) / 4, y = 1.7, h = 2.9;
  const items = [
    ["2.2 pts", "Average amount by which India VIX exceeded the volatility that followed (VIX higher on 78% of days)", C.text2],
    ["9% → 30%", "Nifty's annualised volatility when VIX is below 13 vs above 20", C.accent1],
    ["4.2×", "Jump in a June 22,500 Nifty put on 4 June 2024, election result day", C.accent1],
    ["−22%", "Worst fall with the VIX-timed hedge, vs −38% for unhedged Nifty (2020–2026)", C.accent2],
  ];
  items.forEach(([big, label, col], i) => stat(s, M + i * (cw + 0.3), y, cw, h, big, label, col, { bigH: 0.9, bigSize: 28 }));
  s.addText("Fear is overpriced most of the time and most overpriced just after a shock. So buy protection when VIX is calm and sell it into the spike.",
    { x: M, y: 5.0, w: CW, h: 1.2, fontSize: 20, italic: true, color: C.text2, margin: 0, valign: "middle", isTextBox: true, objectName: "takeaway" });
}
s.addNotes("The volatility risk premium is the starting point: options usually cost more than the volatility that follows. VIX regimes separate risk sharply. The election shows how premiums behave around a scheduled shock. The last number is the backtest headline, which depends heavily on the 2020 crash, as later slides show.");

// ================= 3. Data and method =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Overview" });
s.addText("Real prices, modelled option premiums", { placeholder: "title" });
{
  const cw = (CW - 0.3) / 2, y = 1.5, h = 3.45;
  card(s, M, y, cw, h, C.background2, "data card");
  s.addText("Real market data", { x: M + 0.3, y: y + 0.25, w: cw - 0.6, h: 0.45, fontSize: 20, bold: true, color: C.text2, margin: 0, isTextBox: true });
  s.addText(bullets([
    "Nifty 50 daily closes, Sep 2007 to Apr 2026",
    "India VIX daily closes, Jan 2020 to Aug 2026",
    "Common sample: 1,536 trading days, Jan 2020 to Apr 2026",
    "Checked against NSE: on 4 Jun 2024 Nifty closed at 21,884.50 and VIX at 26.75",
  ]), { x: M + 0.3, y: y + 0.85, w: cw - 0.6, h: h - 1.05, valign: "top", margin: 0, isTextBox: true });
  const x2 = M + cw + 0.3;
  card(s, x2, y, cw, h, C.background2, "model card");
  s.addText("Modelled option premiums", { x: x2 + 0.3, y: y + 0.25, w: cw - 0.6, h: 0.45, fontSize: 20, bold: true, color: C.text2, margin: 0, isTextBox: true });
  s.addText(bullets([
    "Black-Scholes-Merton, risk-free 6.5%, dividend yield 1.3%",
    "Implied vol = India VIX + 0.6 vol pt per 1% out of the money",
    "Bought at +0.5 and sold at −0.5 vol pt to cover bid/ask",
    "Historical NSE option chains were not available",
  ]), { x: x2 + 0.3, y: y + 0.85, w: cw - 0.6, h: h - 1.05, valign: "top", margin: 0, isTextBox: true });

  s.addText("VIX regimes used throughout", { x: M, y: 5.2, w: CW, h: 0.4, fontSize: 16, bold: true, color: C.text2, margin: 0, isTextBox: true });
  const rw = (CW - 2 * 0.3) / 3;
  [["Low: VIX below 13", "27% of days", C.accent2], ["Normal: 13 to 20", "48% of days", C.accent3], ["High: above 20", "25% of days", C.accent1]]
    .forEach(([a, b, col], i) => {
      const x = M + i * (rw + 0.3);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.7, w: rw, h: 0.95, rectRadius: 0.08, fill: { color: col }, line: { type: "none" }, objectName: `regime ${a}` });
      s.addText([{ text: a, options: { bold: true, fontSize: 18, breakLine: true } }, { text: b, options: { fontSize: 14 } }],
        { x: x + 0.25, y: 5.7, w: rw - 0.5, h: 0.95, color: C.background1, valign: "middle", margin: 0, isTextBox: true });
    });
}
s.addNotes("All index levels are actual daily closes from Yahoo Finance mirrors, spot-checked against NSE. Old option-chain prices were not reachable, so premiums are priced with Black-Scholes using India VIX as the volatility, with a put skew and a bid-ask haircut. The results therefore show how options would have been priced at VIX-consistent volatility, not actual traded prices. The regime cut-offs sit near the 30th and 80th percentiles of VIX.");

// ================= 4. VRP =================
pres.addSection({ title: "Volatility and India VIX" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Volatility and India VIX" });
s.addText("VIX usually overstates future volatility", { placeholder: "title" });
img(s, "fig2_vrp.png", M, 1.45, 7.3, 882 / 1426, "India VIX vs realised volatility over the next 21 days, and the gap between them");
barChart(s, ["Low", "Normal", "High"], [2.1, 1.4, 4.0], [HEX.accent2, HEX.accent3, HEX.accent1],
  { x: 8.25, y: 1.45, w: 4.48, h: 2.9, title: "Average VRP by VIX regime (vol points)", min: 0, max: 4.8 });
s.addText(bullets([
  "VRP = VIX minus realised vol over the next 21 days: +2.2 pts on average (t = 2.8)",
  "Largest after shocks (4.0 pts): sell protection then, don't buy it",
  "VIX tracks the past 21 days (corr 0.86) more than the next 21 (0.61)",
]), { x: 8.25, y: 4.55, w: 4.48, h: 2.3, valign: "top", margin: 0, isTextBox: true });
s.addNotes("The blue line is India VIX, the orange line is the volatility Nifty actually delivered over the following month. The lower panel is the difference. It is positive on 78 percent of days. The red periods are when realised volatility exceeded what was priced: early 2020, early 2022, May 2024, March 2025 and early 2026. A forecast regression gives realised vol = 1.05 + 0.81 x VIX, so VIX is informative but biased upward.");

// ================= 5. VIX construction =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Volatility and India VIX" });
s.addText("How India VIX is built", { placeholder: "title" });
{
  const bw = (CW - 3 * 0.3) / 4, y = 1.5, h = 2.65;
  const steps = [
    ["Near and next-month options", "OTM puts below the forward, OTM calls above it, at mid-quotes"],
    ["Variance per expiry", "Weights each option by ΔK/K², so low strikes count most"],
    ["Interpolate to 30 days", "Blend the two expiries to a constant 30-calendar-day horizon"],
    ["Scale to an index", "India VIX = 100 × √(30-day variance), in annualised percent"],
  ];
  steps.forEach(([hd, ds], i) => {
    const x = M + i * (bw + 0.3);
    card(s, x, y, bw, h, C.background2, `step ${i + 1}`);
    numCircle(s, x + 0.25, y + 0.25, 0.55, i + 1, C.text2);
    headDesc(s, x + 0.25, y + 0.95, bw - 0.5, h - 1.1, hd, ds);
  });
  card(s, M, 4.4, CW, 0.9, C.background2, "formula card");
  s.addText("σ² = (2/T) · Σ (ΔKᵢ / Kᵢ²) · e^(RT) · Q(Kᵢ)  −  (1/T) · (F / K₀ − 1)²", { x: M + 0.3, y: 4.4, w: CW - 0.6, h: 0.9, fontSize: 22, color: C.text2, margin: 0, valign: "middle", isTextBox: true, objectName: "formula" });
  const sw = (CW - 0.3) / 2;
  stat(s, M, 5.55, sw, 1.25, "15.0", "", C.text2, { bigH: 0.8, bigSize: 30 });
  s.addText("Formula on a synthetic chain with a flat 15% smile: it recovers the input exactly", { x: M + 1.6, y: 5.55, w: sw - 1.85, h: 1.25, fontSize: 14, color: C.text1, margin: 0, valign: "middle", isTextBox: true });
  stat(s, M + sw + 0.3, 5.55, sw, 1.25, "16.1", "", C.accent1, { bigH: 0.8, bigSize: 30 });
  s.addText("Same 15% at-the-money vol with put skew: VIX also prices crash fear", { x: M + sw + 0.3 + 1.6, y: 5.55, w: sw - 1.85, h: 1.25, fontSize: 14, color: C.text1, margin: 0, valign: "middle", isTextBox: true });
}
s.addNotes("NSE adopted the CBOE methodology in 2008. F is the forward implied by put-call parity, K0 the first strike at or below F, Q(K) the option mid-price and T the time to expiry. Because each option is weighted by one over K squared, out-of-the-money puts carry a lot of weight. The analysis script reproduces the formula on a Black-Scholes chain: a flat 15 percent smile gives exactly 15.0, while adding put skew gives 16.1. So VIX measures both expected volatility and the price of crash insurance.");

// ================= 6. Fear gauge =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Volatility and India VIX" });
s.addText("India VIX as a fear gauge: three traits", { placeholder: "title" });
img(s, "fig1_nifty_vix_regimes.png", M, 1.45, 7.3, 882 / 1425, "Nifty 50 and India VIX, 2020 to 2026, shaded by VIX regime");
{
  const x = 8.25, w = W - M - x;
  const rows = [
    ["Rises when Nifty falls", "+2.3% on an average down day, −1.9% on an up day (correlation −0.56)", C.accent1],
    ["Persists, then mean-reverts", "Regimes last weeks to months, but every spike returned to 12–16", C.text2],
    ["Prices known events early", "VIX climbed for six weeks before the 2024 result while Nifty was flat", C.accent2],
  ];
  rows.forEach(([hd, ds, col], i) => {
    const y = 1.55 + i * 1.75;
    numCircle(s, x, y, 0.55, i + 1, col);
    headDesc(s, x + 0.8, y, w - 0.8, 1.5, hd, ds);
  });
}
s.addNotes("Shading shows the regime: blue below 13, grey 13 to 20, orange above 20. The leverage effect is strong: a 1 percent fall in Nifty comes with about a 2.7 percent rise in VIX. Regimes cluster, which is what makes a regime-based hedge workable. And VIX moves ahead of scheduled events, as the election shows next.");

// ================= 7. Regimes vs returns =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Volatility and India VIX" });
s.addText("VIX regimes separate risk, not return", { placeholder: "title" });
{
  const cw = (CW - 0.3) / 2;
  barChart(s, ["Low", "Normal", "High"], [9.0, 13.2, 30.1], [HEX.accent2, HEX.accent3, HEX.accent1],
    { x: M, y: 1.45, w: cw, h: 3.75, title: "Annualised Nifty volatility by VIX regime (%)", min: 0, max: 35 });
  barChart(s, ["Low", "Normal", "High"], [1.1, -0.2, 3.4], [HEX.accent2, HEX.accent3, HEX.accent1],
    { x: M + cw + 0.3, y: 1.45, w: cw, h: 3.75, title: "Average Nifty return over the next 21 days (%)", min: -1, max: 4.2 });
  s.addText(bullets([
    "Volatility differs by regime (Levene p < 0.001), but same-day returns do not (Kruskal-Wallis p = 0.66)",
    "High VIX was followed by rebounds: +0.18% next-21-day return per VIX point (t = 4.3), mostly the 2020 recovery",
    "Worst 63-day outcomes began in the Normal regime (5th percentile −14.6%), so protection must be in place before VIX rises",
  ]), { x: M, y: 5.4, w: CW, h: 1.5, valign: "top", margin: 0, isTextBox: true });
}
s.addNotes("Volatility triples from the low to the high regime. Mean returns do not differ significantly on the same day. Forward returns overlap, so t-statistics use Newey-West errors. Low-VIX periods had positive but modest forward returns, normal-VIX periods were flat, and high-VIX periods were followed by strong rebounds. With six years of data these return differences are imprecise; the volatility differences are robust.");

// ================= 8. Election timeline =================
pres.addSection({ title: "4 June 2024" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "4 June 2024" });
s.addText("4 June 2024: build-up, spike, collapse", { placeholder: "title" });
img(s, "fig4_election_window.png", M, 1.45, 6.8, 1106 / 1415, "Nifty, India VIX and the 30-day ATM straddle, April to July 2024");
{
  const x = 7.75, w = W - M - x;
  const rows = [
    ["Late Apr to 31 May: run-up", "VIX 10.2 → 24.6 with Nifty flat; 30-day straddle 2.4% → 5.6% of spot", C.text2],
    ["3 June: exit polls", "Nifty +3.25%, VIX −15%: protection was cheapest just before the shock", C.accent2],
    ["4 June: result", "Nifty −5.93% (−8.5% intraday), VIX 26.75; June 22,500 put up 4.2×", C.accent1],
    ["5 to 7 June: vol crush", "VIX −29% next day as Nifty rebounded 3.4%; straddle back to 3.9%", C.accent3],
  ];
  rows.forEach(([hd, ds, col], i) => {
    const y = 1.5 + i * 1.33;
    numCircle(s, x, y, 0.5, i + 1, col);
    headDesc(s, x + 0.75, y, w - 0.75, 1.25, hd, ds);
  });
}
s.addNotes("This is the typical pattern for a scheduled event. The 30-day ATM straddle, modelled from VIX, more than doubled during the run-up even though Nifty did not move. Exit polls predicted a large majority and premiums fell. The result was a surprise and the modelled 27 June 22,500 put went from 217 to 903 points in a day. One day later most of the premium was gone even though Nifty was still below its pre-result level.");

// ================= 9. Event comparison =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "4 June 2024" });
s.addText("Priced the size, not the direction", { placeholder: "title" });
{
  const rows = [
    ["Election result (Jun 2024)", "−5.93%", "20.9 → 26.8", "4.8 → 6.1", "4.6×"],
    ["Exit polls (Jun 2024)", "+3.25%", "24.6 → 20.9", "5.6 → 4.8", "2.1×"],
    ["US tariffs (Apr 2025)", "−3.24%", "13.8 → 22.8", "3.2 → 5.2", "3.8×"],
    ["Yen carry (Aug 2024)", "−2.68%", "14.3 → 20.4", "3.3 → 4.7", "3.0×"],
    ["Ukraine (Feb 2022)", "−4.78%", "24.5 → 32.0", "5.6 → 7.3", "3.2×"],
    ["COVID (Mar 2020)", "−12.98%", "67.1 → 72.0", "15.3 → 16.4", "3.3×"],
    ["Normal day (median)", "±0.47%", "14.7", "3.4", "0.5×"],
  ];
  s.addTable(tableRows(["Day", "Nifty move", "VIX", "Straddle, % of spot", "Move vs implied"], rows),
    Object.assign({ x: M, y: 1.5, w: 8.9, colW: [3.0, 1.25, 1.6, 1.7, 1.35], rowH: 0.5, objectName: "event table" }, tableStyle));
  s.addText("Straddle = 30-day at-the-money, modelled from VIX. Move vs implied = absolute move ÷ (previous day's VIX ÷ √252).",
    { x: M, y: 5.95, w: 8.9, h: 0.6, fontSize: 12, color: C.text2, margin: 0, valign: "top", isTextBox: true });
  const x = 9.8, w = W - M - x;
  stat(s, x, 1.5, w, 1.65, "5.8%", "Move implied by the 31 May VIX (normal VIX 14.4)", C.text2, { bigH: 0.6, bigSize: 30 });
  stat(s, x, 3.4, w, 1.65, "5.9%", "Actual fall on 4 June", C.accent1, { bigH: 0.6, bigSize: 30 });
  stat(s, x, 5.3, w, 1.5, "4.6×", "Largest move vs implied in the sample", C.accent1, { bigH: 0.6, bigSize: 30 });
}
s.addNotes("If all the extra variance in the pre-election VIX belongs to one day, the implied event move is the square root of (VIX before squared times 30 minus normal VIX squared times 29) divided by 365. That gives 5.8 percent from the 31 May VIX and 4.4 percent from the 3 June VIX, against an actual 5.9 percent. Unlike the unscheduled shocks of 2024 and 2025, which hit when VIX was near 14, the election arrived with VIX already high. Across the 20 largest one-day VIX jumps, VIX rose 28 percent on average, Nifty fell 3.2 percent and the straddle rose 1.3 percent of spot.");

// ================= 10. Strategy rules =================
pres.addSection({ title: "Strategy and backtest" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Strategy and backtest" });
s.addText("Proposed hedge: buy in calm, sell into fear", { placeholder: "title" });
{
  const bw = (CW - 4 * 0.25) / 5, y = 1.5, h = 2.95;
  const steps = [
    ["Buy", "VIX below 13 at month start: buy a 3-month put 5% below spot on the whole portfolio", BLUE_TINT, C.accent2],
    ["Roll", "While VIX stays below 13, swap it each month for a fresh 3-month put", BLUE_TINT, C.accent2],
    ["Wait", "VIX 13 or above: buy nothing new and hold the existing put to expiry", "EEF2F7", C.text2],
    ["Sell half", "First close with VIX at 22 or more: sell 50% of the puts", ORANGE_TINT, C.accent1],
    ["Sell the rest", "VIX 20% below its post-spike peak: sell the rest and reinvest in Nifty", ORANGE_TINT, C.accent1],
  ];
  steps.forEach(([hd, ds, fill, col], i) => {
    const x = M + i * (bw + 0.25);
    card(s, x, y, bw, h, fill, `rule ${hd}`);
    numCircle(s, x + 0.25, y + 0.25, 0.5, i + 1, col);
    headDesc(s, x + 0.25, y + 0.9, bw - 0.5, h - 1.05, hd, ds, { headSize: 18 });
  });
  const ww = (CW - 2 * 0.3) / 3, y2 = 4.75, h2 = 2.0;
  [["Options are cheapest in calm markets", "Low regime: VIX averaged 11.7 and realised vol 9.5%"],
   ["Fear is most overpriced after a spike", "VRP of 4.0 pts in the high regime: the time to sell, not buy"],
   ["Three months buys time", "Slower decay and more vega than 1-month puts, and it survives a lag between signal and crash"]]
    .forEach(([hd, ds], i) => {
      const x = M + i * (ww + 0.3);
      card(s, x, y2, ww, h2, C.background2, `why ${i + 1}`);
      headDesc(s, x + 0.3, y2 + 0.25, ww - 0.6, h2 - 0.4, hd, ds);
    });
}
s.addNotes("The rule is mechanical and can be run from a daily VIX feed. In the backtest, the put bought on 2 January 2020 at VIX 11.5 cost 93 points. Half was sold on 28 February at VIX 23 for 546 points, the rest on 31 March at VIX 64 for 3,050 points. The put bought on 1 April 2024 cost 195 points; half was sold for 177 during the pre-election run-up and the rest for 95 after the vol crush, a small loss because Nifty closed above the strike even on result day.");

// ================= 11. Backtest headline =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Strategy and backtest" });
s.addText("Backtest: higher return, smaller falls", { placeholder: "title" });
img(s, "fig6_backtest_equity.png", M, 1.45, 7.6, 978 / 1426, "Growth of 1 and drawdowns for each hedging strategy, 2020 to 2026");
{
  const x = 8.55, w = W - M - x, h = 1.2;
  [["13.9% vs 11.1%", "Annual return vs unhedged", C.accent2],
   ["−22% vs −38%", "Max drawdown vs unhedged", C.accent2],
   ["2.9% vs 7.5%", "Premium a year vs always-on put", C.text2],
   ["45%", "Share of days holding puts", C.text2]]
    .forEach(([big, lab, col], i) => stat(s, x, 1.45 + i * (h + 0.15), w, h, big, lab, col, { bigH: 0.5, bigSize: 26 }));
}
s.addNotes("The thick blue line is the proposal, black is unhedged Nifty. All returns exclude dividends. Most of the gap opened in March 2020, when the January put paid out and the proceeds were reinvested near the bottom. After that the lines move almost in parallel.");

// ================= 12. Strategy comparison =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Strategy and backtest" });
s.addText("Always-on hedges cost more than they saved", { placeholder: "title" });
{
  const labels = ["Unhedged", "Always 1M put", "Always 1M put spread", "Always 3M put", "Timed 3M, hold", "Timed 3M, proposed", "Timed 3M, sell at 22"];
  const cols = [HEX.dk2, HEX.accent3, HEX.accent3, HEX.accent3, HEX.accent3, HEX.accent2, HEX.accent3];
  const cw = (CW - 0.3) / 2;
  barChart(s, labels, [11.1, 8.3, 7.3, 6.3, 17.2, 13.9, 11.0], cols,
    { x: M, y: 1.45, w: cw, h: 4.6, dir: "bar", title: "Annual return, 2020–2026 (%)", min: 0, max: 20 });
  barChart(s, labels, [38.4, 19.6, 30.2, 17.9, 17.2, 22.0, 35.9], cols,
    { x: M + cw + 0.3, y: 1.45, w: cw, h: 4.6, dir: "bar", title: "Maximum drawdown, 2020–2026 (% fall)", min: 0, max: 45 });
  s.addText("Net option cost a year: 3.0% to 4.9% for always-on hedges, −4.4% to +0.2% for timed hedges (negative means the options returned more than they cost).",
    { x: M, y: 6.2, w: CW, h: 0.65, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true });
}
s.addNotes("Always-on hedges did cut drawdowns, but at 3 to 5 percent of the portfolio a year they gave up more return than they saved. 'Timed, hold' looks best because it held the whole January 2020 put through the crash; that depends on one event, as the robustness slide shows. The proposal sells half early to lock in gains, which costs some upside in a crash but helps in short spikes. Sharpe ratios at a 6.5 percent risk-free rate: unhedged 0.25, proposed 0.48.");

// ================= 13. Cost by regime =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Strategy and backtest" });
s.addText("Hedges bought in calm markets paid", { placeholder: "title" });
s.addChart(pres.charts.BAR, [
  { name: "Always 1M put", labels: ["Bought in Low VIX", "Bought in Normal VIX", "Bought in High VIX"], values: [-0.7, -1.7, -0.6] },
  { name: "Always 1M put spread", labels: ["Bought in Low VIX", "Bought in Normal VIX", "Bought in High VIX"], values: [-0.7, -1.6, -1.4] },
  { name: "Always 3M put", labels: ["Bought in Low VIX", "Bought in Normal VIX", "Bought in High VIX"], values: [-0.9, -1.2, -2.7] },
  { name: "Proposed (buys only in Low)", labels: ["Bought in Low VIX", "Bought in Normal VIX", "Bought in High VIX"], values: [2.2, null, null] },
], Object.assign({
  x: M, y: 1.45, w: 7.6, h: 5.35, barDir: "col", barGrouping: "clustered", barGapWidthPct: 50,
  showTitle: true, title: "Net option P&L by VIX regime at purchase (% of portfolio a year)",
  chartColors: [HEX.accent1, HEX.accent4, HEX.accent5, HEX.accent2],
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0",
  valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" },
  catAxisLineShow: true, catAxisLineColor: HEX.accent3, catAxisLabelPos: "low",
  showLegend: true, legendPos: "b", valAxisMinVal: -3.5, valAxisMaxVal: 3, objectName: "cost by regime chart",
}, chartText));
{
  const x = 8.55, w = W - M - x, h = 1.18;
  s.addText("Proposed hedge vs unhedged, by the regime of each day", { x, y: 1.45, w, h: 0.65, fontSize: 16, bold: true, color: C.text2, margin: 0, valign: "top", isTextBox: true });
  [["−2.1% a year", "Low-VIX days: the insurance carry", C.accent2],
   ["+2.0% a year", "Normal-VIX days", C.text2],
   ["+6.3% a year", "High-VIX days, when puts pay out", C.accent1],
   ["−9.2% a year", "Always-on put on high-VIX days", C.text2]]
    .forEach(([big, lab, col], i) => stat(s, x, 2.2 + i * 1.17, w, 1.05, big, lab, col, { bigH: 0.42, bigSize: 22 }));
}
s.addNotes("Each option's whole life, premium paid less money received, is attributed to the VIX regime on the day it was bought. Every always-on hedge lost money in every regime, and most in the normal and high regimes where premiums are rich. The proposal only buys in the low regime, and those purchases returned 2.2 percent of the portfolio a year net. The right-hand panel shows the same idea day by day.");

// ================= 14. Stress episodes =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Strategy and backtest" });
s.addText("Protection works from a calm start", { placeholder: "title" });
{
  const rows = [
    ["COVID crash, 17 Jan to 23 Mar 2020", "−38.4%", "−15.5%", "−12.4%", "−21.1%"],
    ["War and rate hikes, Jan to Jun 2022", "−16.5%", "−17.1%", "−13.9%", "−16.5%"],
    ["Election result, 3 to 4 Jun 2024", "−5.9%", "−3.6%", "−3.1%", "−5.2%"],
    ["Yen-carry unwind, 1 to 5 Aug 2024", "−3.8%", "−2.6%", "−1.9%", "−1.9%"],
    ["Slow correction, Sep 2024 to Mar 2025", "−15.8%", "−16.3%", "−14.7%", "−15.4%"],
    ["Tariff shock, 28 Mar to 7 Apr 2025", "−5.8%", "−4.3%", "−3.4%", "−5.8%"],
  ];
  s.addTable(tableRows(["Episode (portfolio return)", "Unhedged", "Always 1M put", "Always 3M put", "Proposed"], rows, 4),
    Object.assign({ x: M, y: 1.5, w: CW, colW: [4.53, 1.9, 1.9, 1.9, 1.9], rowH: 0.52, objectName: "episode table" }, tableStyle));
  const cw = (CW - 0.3) / 2, y = 5.35, h = 1.45;
  card(s, M, y, cw, h, BLUE_TINT, "works card");
  headDesc(s, M + 0.3, y + 0.2, cw - 0.6, h - 0.3, "Works: shocks from a calm start", "January 2020 and August 2024 began with VIX near or below 13, so a cheap put was already held");
  card(s, M + cw + 0.3, y, cw, h, ORANGE_TINT, "fails card");
  headDesc(s, M + cw + 0.6, y + 0.2, cw - 0.6, h - 0.3, "Fails: slow grinds, or VIX already rising", "2022, late 2024 and April 2025 started with VIX in the normal band, so no hedge was bought");
}
s.addNotes("The timed hedge is insurance against one kind of event: a sudden shock from a calm market. It gives nothing in a slow decline or when VIX has already risen before the drop. Always-on puts protect more often, but over this period their cost exceeded what they saved.");

// ================= 15. Robustness =================
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Strategy and backtest" });
s.addText("What the result depends on", { placeholder: "title" });
img(s, "fig8_sensitivity.png", M, 1.5, 7.4, 542 / 1507, "Sensitivity of return and drawdown to entry and monetisation thresholds");
s.addText("Buying only below VIX 12 to 15 beat buying regardless of VIX in every cell: 12.2–15.7% a year against 5.9–8.5%, with drawdowns of about −20% to −22%.",
  { x: M, y: 4.35, w: 7.4, h: 1.0, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true });
s.addText("Pricing check: with skew of 0 to 1 vol pt per 1% and half-spreads of 0 to 1 pt, the proposal returned 12.9–15.1% vs 6.0–11.1% for the always-on put.",
  { x: M, y: 5.45, w: 7.4, h: 1.0, fontSize: 14, color: C.text1, margin: 0, valign: "top", isTextBox: true });
{
  const x = 8.35, w = W - M - x, h = 1.65;
  [["Robust: buy only in low VIX", "Holds across thresholds, skew and bid/ask assumptions", BLUE_TINT],
   ["Fragile: tenor", "1 to 2-month puts expired before the March 2020 crash: about 10.5% a year with −36% drawdown", ORANGE_TINT],
   ["Fragile: one crash", "Jul 2020 to Apr 2026: 14.9% vs 15.4% unhedged, same −17.2% drawdown. Cost about 0.5% a year", ORANGE_TINT]]
    .forEach(([hd, ds, fill], i) => {
      const y = 1.5 + i * (h + 0.2);
      card(s, x, y, w, h, fill, hd);
      headDesc(s, x + 0.25, y + 0.18, w - 0.5, h - 0.3, hd, ds);
    });
}
s.addNotes("The monetisation rule also matters. With 3-month puts, holding to expiry returned 17.2 percent, a trailing rule 16.5, the hybrid 13.9, a 22/30 ladder 11.9 and selling everything at 22 only 11.0. Selling early wins in short scheduled spikes; holding wins in a crash that keeps going. The hybrid is a compromise because nobody knows in advance which kind of spike it is.");

// ================= 16. Limitations =================
pres.addSection({ title: "Limitations and conclusion" });
s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Limitations and conclusion" });
s.addText("Limitations", { placeholder: "title" });
{
  const cw = (CW - 0.3) / 2, h = 2.45;
  [["Modelled premiums", "Priced from India VIX, not traded quotes. Real 3-month puts in calm markets probably cost more, because the term structure slopes up and skew is steeper."],
   ["Short history", "India VIX data here starts in 2020: one true crash, and thresholds set on the same data they are tested on."],
   ["Synthetic expiries", "Options expire on the first trading day of each month, not on NSE expiry days. The results show timing can matter a lot."],
   ["Costs left out", "No dividends, taxes, STT, brokerage or margin. All trades at the daily close."]]
    .forEach(([hd, ds], i) => {
      const x = M + (i % 2) * (cw + 0.3), y = 1.5 + Math.floor(i / 2) * (h + 0.3);
      card(s, x, y, cw, h, C.background2, hd);
      numCircle(s, x + 0.3, y + 0.3, 0.55, i + 1, C.text2);
      headDesc(s, x + 1.1, y + 0.3, cw - 1.4, h - 0.5, hd, ds, { headSize: 18 });
    });
}
s.addNotes("The skew and spread sensitivities bound the pricing assumption but do not remove it. A longer India VIX history, back to 2008, would add the global financial crisis and the 2011 and 2015 to 2016 drawdowns and would be the first extension to make.");

// ================= 17. Conclusion =================
s = pres.addSlide({ masterName: "CLOSING_DARK", sectionTitle: "Limitations and conclusion" });
s.addText("Buy protection cheap, sell it into fear", { placeholder: "title" });
s.addText(bullets([
  "Nifty option buyers pay about 2 vol points of risk premium, and about 4 points just after shocks",
  "India VIX is a good real-time gauge of fear and of option prices, not of market direction",
  "Event premiums build for weeks and collapse within a day, as on 4 June 2024",
  "A VIX-timed 3-month put costs about 0.5% a year in calm periods and cut the 2020–26 drawdown from 38% to 22%",
], 20, C.background1), { x: M, y: 1.9, w: 7.6, h: 4.8, valign: "top", margin: 0, isTextBox: true, objectName: "conclusions" });
{
  const x = 8.6, w = W - M - x, y = 1.9, h = 3.9;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.accent1 }, line: { type: "none" }, objectName: "recommendation card" });
  s.addText([
    { text: "Recommendation", options: { bold: true, fontSize: 22, breakLine: true, paraSpaceAfter: 10 } },
    { text: "Treat the VIX-timed put as cheap crash insurance that pays rarely, not as a source of return. Use 3-month tenors and sell half into the first spike.", options: { fontSize: 18 } },
  ], { x: x + 0.35, y: y + 0.35, w: w - 0.7, h: h - 0.7, color: C.background1, valign: "top", margin: 0, isTextBox: true });
}
s.addNotes("Summing up: options are usually overpriced, most of all after a shock. VIX regimes tell you about risk, not return. Scheduled events like the election follow a build-up, spike and crush pattern. The practical recommendation for a long-term Nifty investor is to buy 3-month out-of-the-money puts only when VIX is below 13, and monetise them when VIX spikes.");

(async () => {
  await pres.writeFile({ fileName: OUT });
  if (applyTheme) await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();

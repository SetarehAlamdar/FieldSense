// FieldSense demo page.
// Reads data/index.json (list of fields), data/evidence.json, and data/<field>.json
// (public field profiles made by fieldsense.export). No server code: plain files.

const DATA = "data/";
const SVGNS = "http://www.w3.org/2000/svg";
const LABEL_TEXT = {
  measured: "Observed directly at this field",
  validated: "Modelled, then checked against independent ground truth",
  modelled: "From a model not checked at this field",
  assumed: "From literature or expert rules, not tested here",
};
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_START = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
const ROT_NAMES = {
  "CSS": "Corn – soybean – soybean",
  "CSS+rye": "Corn – soybean – soybean + rye",
  "SWC": "Soybean – wheat – corn",
  "SWC+covers": "Soybean – wheat + clover – corn + rye",
};

let evidence = {};
document.documentElement.classList.add("js");

// ---------- small helpers
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) k === "class" ? (n.className = v) : n.setAttribute(k, v);
  for (const k of kids) n.append(k instanceof Node ? k : document.createTextNode(k));
  return n;
};
const svg = (tag, attrs = {}) => {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};
const badge = (label) => el("span", { class: `badge ${label}`, title: LABEL_TEXT[label] || "" }, label || "unknown");
const evLabel = (id) => (evidence[id] && evidence[id].label) || null;
const pct = (x) => `${Math.round(100 * x)}%`;
// image address; in the single-file preview, images are packed inside the page (__I)
const asset = (name) => ((typeof __I !== "undefined" && __I[DATA + name]) || DATA + name);
const nice = (t) => (t || "").replace(/ ?degC/g, " °C");
const show = (id) => { $(id).hidden = false; };

function doyToDate(doy) {
  const d = new Date(Date.UTC(2025, 0, 1));          // a non-leap year
  d.setUTCDate(Math.round(doy));
  return d.toLocaleDateString("en-CA", { month: "short", day: "numeric", timeZone: "UTC" });
}

function shortCrop(s) {
  return s.replace("corn or soybean", "corn/soy").replace("winter wheat", "wheat")
    .replace(/ \((overwintered )?cover crop\?\)/g, "")
    .replace("green in spring, green after harvest", "spring + fall cover")
    .replace("green in spring", "spring cover").replace("green after harvest", "fall cover");
}

// Greenness colour scale: brown (bare) -> pale -> green (dense crop), same as the Python figure.
const STOPS = [[0.1, [140, 90, 43]], [0.3, [217, 196, 140]], [0.5, [201, 221, 138]], [0.7, [90, 160, 64]], [0.9, [31, 107, 42]]];
function green(v) {
  if (v <= STOPS[0][0]) return `rgb(${STOPS[0][1]})`;
  for (let i = 1; i < STOPS.length; i++) {
    if (v <= STOPS[i][0]) {
      const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i], t = (v - a) / (b - a);
      return `rgb(${ca.map((c, j) => Math.round(c + t * (cb[j] - c))).join(",")})`;
    }
  }
  return `rgb(${STOPS[STOPS.length - 1][1]})`;
}

// ---------- sections
function renderGlance(p) {
  const g = $("glance-grid");
  g.replaceChildren();
  const ro = p.rotation_options || {};
  const cov = p.cover || {};
  const cl = p.climate || {};
  const stat = (k, v, s, ev) => {
    const box = el("div", { class: "stat" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v));
    if (s || ev) box.append(el("div", { class: "s" }, s || "", ev ? " " : "", ev ? badge(ev) : ""));
    g.append(box);
  };
  if (ro.current) stat("Rotation now", ROT_NAMES[ro.current] || ro.current, "read from satellite history", evLabel("hls_crop_history"));
  const nxt = ro.next_crop || ro.next_crop_2026;
  if (nxt) stat(`In ${ro.next_season || 2026}`, nxt.split(" (")[0], nxt.includes("(") ? "satellite can't tell which; ask the farmer" : "next in the cycle", evLabel("hls_crop_history"));
  if (cov.recent_green_share_off_season != null) stat("Off-season living cover", pct(cov.recent_green_share_off_season), "share of off-season days green, last 5 years", "measured");
  if (cl.frost_free_days) stat("Frost-free season", `${Math.round(cl.frost_free_days.mid)} days`, `${Math.round(cl.frost_free_days.low)}–${Math.round(cl.frost_free_days.high)} in 8 of 10 years`, cl.frost_free_days.evidence && evLabel(cl.frost_free_days.evidence));
  if (cl.annual_precip) stat("Rain per year", `${Math.round(cl.annual_precip.mid)} mm`, `${Math.round(cl.annual_precip.low)}–${Math.round(cl.annual_precip.high)} in 8 of 10 years`, cl.annual_precip.evidence && evLabel(cl.annual_precip.evidence));
  if (p.soil && p.soil.texture_class) stat("Topsoil", p.soil.texture_class.class, "SoilGrids prediction", evLabel(p.soil.texture_class.evidence));
  show("glance");
}

function renderBarcode(p) {
  const bc = p.barcode;
  if (!bc || !bc.values) return;
  const box = $("barcode");
  box.replaceChildren();
  const rowH = 22, gap = 4, left = 44, labelW = 170, top = 20;
  const W = left + 365 + labelW, H = top + bc.years.length * (rowH + gap);
  box.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const labels = Object.fromEntries((p.history || []).map((h) => [h.year, shortCrop(h.satellite_says)]));
  MONTH_START.forEach((d, i) => {
    const t = svg("text", { x: left + d - 1, y: 12, "font-size": 10, fill: "var(--muted)" });
    t.textContent = MONTHS[i];
    box.append(t);
  });
  bc.years.forEach((year, r) => {
    const y = top + r * (rowH + gap);
    const yl = svg("text", { x: left - 6, y: y + rowH / 2 + 4, "font-size": 11, "text-anchor": "end", fill: "var(--ink)" });
    yl.textContent = year;
    box.append(yl);
    box.append(svg("rect", { x: left, y, width: 365, height: rowH, fill: "var(--none)" }));
    // merge runs of equal colour into one rect: far fewer elements than one per day
    const row = bc.values[r];
    let start = 0;
    for (let d = 1; d <= 365; d++) {
      const prev = row[d - 1], cur = d < 365 ? row[d] : undefined;
      const same = d < 365 && (prev === null ? cur === null : cur !== null && Math.round(prev / 4) === Math.round(cur / 4));
      if (!same) {
        if (prev !== null) box.append(svg("rect", { x: left + start, y, width: d - start + 0.4, height: rowH, fill: green(prev / bc.scale) }));
        start = d;
      }
    }
    const lab = svg("text", { x: left + 372, y: y + rowH / 2 + 4, "font-size": 11, fill: "var(--muted)" });
    lab.textContent = labels[year] || "";
    box.append(lab);
  });
  const tip = $("tip");
  box.onmousemove = (e) => {
    const pt = box.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const q = pt.matrixTransform(box.getScreenCTM().inverse());
    const day = Math.floor(q.x - left), r = Math.floor((q.y - top) / (rowH + gap));
    if (day < 0 || day >= 365 || r < 0 || r >= bc.years.length) { tip.hidden = true; return; }
    const v = bc.values[r][day];
    const rect = box.getBoundingClientRect(), host = box.parentElement.getBoundingClientRect();
    tip.textContent = `${doyToDate(day + 1)} ${bc.years[r]} · ${v === null ? "no clear view" : "greenness " + (v / bc.scale).toFixed(2)}`;
    tip.style.left = `${e.clientX - host.left}px`; tip.style.top = `${e.clientY - host.top}px`;
    tip.hidden = false;
  };
  box.onmouseleave = () => { tip.hidden = true; };
  $("barcode-evidence").replaceChildren("NASA HLS (Landsat + Sentinel-2) pixels inside the field ", badge("measured"),
    " · crop labels checked against field records ", badge(evLabel("hls_crop_history") || "modelled"));
  show("barcode-section");
}

function renderCoverChart(p) {
  const rows = ((p.cover || {}).per_year || []).filter((r) => r.green_share_off_season != null);
  const box = $("cover-chart");
  box.replaceChildren();
  if (!rows.length) return;
  const chart = el("div", { class: "cover-chart", role: "img",
    "aria-label": "Share of off-season days green, per year: " + rows.map((r) => `${r.year} ${pct(r.green_share_off_season)}`).join(", ") });
  const years = el("div", { class: "cover-years" });
  for (const r of rows) {
    const bar = el("div", { class: "bar-v", title: `${r.year}: ${pct(r.green_share_off_season)} of ${r.observed_days_off_season} observed off-season days` });
    bar.style.height = `${Math.max(1, 100 * r.green_share_off_season)}%`;
    chart.append(el("div", { class: "cover-col" }, el("span", { class: "val" }, pct(r.green_share_off_season)), bar));
    years.append(el("span", {}, `'${String(r.year).slice(2)}`));
  }
  box.append(chart, years);
}

function renderFigures(figures) {
  if (!figures || !figures.length) return;
  $("figures").replaceChildren(...figures.map((f) => el("figure", { class: "figure" },
    el("a", { href: asset(f.file), target: "_blank", rel: "noopener", title: "Open full size" }, el("img", { src: asset(f.file), alt: f.title })),
    el("figcaption", {}, el("strong", {}, f.title), f.caption))));
  show("figures-section");
}

function renderOdds(p) {
  const odds = p.climate_odds;
  if (!odds) return;
  const grid = $("odds-grid");
  grid.replaceChildren();
  for (const [key, r] of Object.entries(odds.risks)) {
    if (r.text.startsWith("(deprecated)")) continue;
    const k = Math.round(100 * r.share);
    const icons = svg("svg", { viewBox: "0 0 100 100", role: "img", "aria-label": `${k} in 100` });
    for (let i = 0; i < 100; i++) {
      icons.append(svg("rect", { x: (i % 10) * 10 + 1, y: Math.floor(i / 10) * 10 + 1, width: 8, height: 8, rx: 1.5,
        fill: i < k ? "var(--risk)" : "var(--empty)" }));
    }
    grid.append(el("div", { class: "odd" },
      el("div", { class: "n" }, `${k} `, el("small", {}, "in 100 seasons")), icons,
      el("div", { class: "t" }, (r.text.charAt(0).toUpperCase() + r.text.slice(1)).replace(/ ?degC/g, " °C")),
      el("div", { class: "p" }, `Happened in ${r.past_years} past years`)));
  }
  const labels = (odds.risks[Object.keys(odds.risks)[0]].evidence || []).map((id) => evLabel(id)).filter(Boolean);
  const weakest = ["assumed", "modelled", "validated", "measured"].find((l) => labels.includes(l));
  $("odds-evidence").replaceChildren("Rain and temperature ", badge("validated"), " against Environment Canada stations; risk thresholds are agronomic rules of thumb ",
    badge("assumed"), weakest ? `, so the odds are only as strong as their weakest link: ${weakest}.` : ".");
  show("odds-section");
}

const COLS = [
  ["green_share_off_season", "Off-season living cover", +1, pct],
  ["spring_bare_share", "Bare in spring storms", -1, pct],
  ["climate_risk_total", "Next-season risk-hits /100 crop-years", -1, (v) => Math.round(v)],
  ["legume_share", "Legume years", +1, pct],
  ["min_years_between_same_crop", "Pest break (years)", +1, (v) => v],
  ["crops_to_manage", "Crops to manage", -1, (v) => v],
];

function renderRotations(p) {
  const ro = p.rotation_options;
  if (!ro) return;
  const t = $("tradeoff");
  t.replaceChildren();
  const head = el("tr", {}, el("th", {}, "Rotation"));
  COLS.forEach(([, label, dir]) => head.append(el("th", {}, label, el("br"), dir > 0 ? "higher is better" : "lower is better")));
  t.append(el("thead", {}, head));
  const best = Object.fromEntries(COLS.map(([k, , dir]) => [k, (dir > 0 ? Math.max : Math.min)(...ro.candidates.map((c) => c[k]))]));
  const body = el("tbody");
  for (const c of ro.candidates) {
    const isCur = c.key === ro.current;
    const tr = el("tr", { class: isCur ? "current" : "" }, el("td", {}, ROT_NAMES[c.key] || c.name, isCur ? el("span", { class: "tag" }, "NOW") : ""));
    COLS.forEach(([k, , , fmt]) => {
      const coverCol = k === "green_share_off_season" || k === "spring_bare_share";
      const mark = coverCol && c.cover_evidence ? el("span", { class: `dot ${c.cover_evidence}`, title: c.cover_evidence === "measured" ? "measured by satellite" : "estimated from the crop calendar" }) : "";
      tr.append(el("td", { class: c[k] === best[k] ? "best" : "" }, String(fmt(c[k])), mark));
    });
    body.append(tr);
  }
  t.append(body);
  const rb = $("robust");
  rb.replaceChildren();
  for (const [k, v] of Object.entries(ro.robustness_best_share || {})) {
    const bar = el("div", { class: "bar" }, el("span"));
    bar.firstChild.style.width = `${100 * v}%`;
    rb.append(el("div", { class: "bar-row" }, el("span", {}, ROT_NAMES[k] || k), bar, el("span", {}, pct(v))));
  }
  $("not-included").replaceChildren(
    el("span", { class: "dot measured" }), " Soil cover for this field's current rotation is ", badge("measured"), ` by satellite${ro.measured_since ? " since " + ro.measured_since : ""}. `,
    el("span", { class: "dot modelled" }), " For rotations it hasn't tried, it comes from a crop-calendar model ", badge(ro.calendar_model_evidence || "modelled"), ". ",
    `Not included yet: ${(ro.not_included || []).join(", ")}. Leaving out costs makes diverse rotations look better than many farmers would find them.`);
  show("rotation-section");
}

const PARTS = [["what", "What it is"], ["soil_cover", "Soil cover"], ["climate_2026", "Climate next season"],
  ["nutrients_pests", "Nutrients & pests"], ["unknowns", "What we don't know"]];

function renderExplanations(p) {
  const ro = p.rotation_options;
  if (!ro || !ro.explanations) return;
  const grid = $("explain-grid");
  grid.replaceChildren();
  for (const [key, ex] of Object.entries(ro.explanations)) {
    const dl = el("dl");
    for (const [part, title] of PARTS) {
      if (!ex[part]) continue;
      dl.append(el("dt", {}, title, " ", badge(ex[part].evidence)), el("dd", {}, ex[part].text));
    }
    grid.append(el("div", { class: "explain" }, el("h3", {}, key === ro.current ? "Now: " : "Alternative: ", ROT_NAMES[key] || key), dl));
  }
  show("explain-section");
}

// ---------- How FieldSense decides (4 steps + live priorities)
const PRIORITIES = [
  { key: "soil", label: "Protect the soil", crit: [["green_share_off_season", +1], ["spring_bare_share", -1]] },
  { key: "weather", label: "Avoid weather risk", crit: [["climate_risk_total", -1]] },
  { key: "nutrients", label: "Nitrogen & pest break", crit: [["legume_share", +1], ["min_years_between_same_crop", +1]] },
  { key: "simple", label: "Keep it simple", crit: [["crops_to_manage", -1]] },
];
const weights = { soil: 50, weather: 50, nutrients: 50, simple: 50 };

function scoreRotations(cands) {
  const norm = {};
  for (const pr of PRIORITIES) for (const [k, dir] of pr.crit) {
    const xs = cands.map((c) => dir * c[k]);
    const lo = Math.min(...xs), hi = Math.max(...xs);
    norm[k] = Object.fromEntries(cands.map((c) => [c.key, hi > lo ? (dir * c[k] - lo) / (hi - lo) : 0.5]));
  }
  const total = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
  return cands.map((c) => ({
    key: c.key,
    score: PRIORITIES.reduce((s, pr) => s + weights[pr.key] * pr.crit.reduce((a, [k]) => a + norm[k][c.key], 0) / pr.crit.length, 0) / total,
  })).sort((a, b) => b.score - a.score);
}

function renderDecide(p) {
  const ro = p.rotation_options;
  if (!ro || !ro.candidates) return;
  const cands = ro.candidates;
  const name = (k) => ROT_NAMES[k] || k;
  const storm = (p.climate_odds && p.climate_odds.risks && p.climate_odds.risks.heavy_rain_on_bare_soil) || null;
  const bars = (vals, fmt, cls) => el("div", { class: "mini-bars" }, ...vals.map(([k, v, max]) => {
    const bar = el("div", { class: "mb-bar" }, el("span"));
    bar.firstChild.style.width = `${Math.max(2, 100 * v / (max || 1))}%`;
    return el("div", { class: `mb-row ${k === ro.current ? "now" : ""} ${cls ? cls(k) : ""}` },
      el("div", { class: "mb-name" }, name(k), k === ro.current ? el("span", { class: "tag" }, "NOW") : ""), bar, el("div", { class: "mb-val" }, fmt(v)));
  }));
  const step = (n, title, text, body) => el("li", { class: "step4" }, el("div", { class: "step-n" }, String(n)),
    el("div", { class: "step-body" }, el("h3", {}, title), el("p", {}, text), body || ""));

  // step 1: the field's past
  const yrs = (p.history || []).map((h) => h.year);
  const wheatYears = (p.history || []).filter((h) => h.satellite_says.startsWith("winter wheat")).map((h) => h.year);
  const s1 = step(1, "Read the field's past from space",
    `${yrs.length} years of NASA satellite greenness show what grew and when the soil was bare` +
    (wheatYears.length ? `: winter wheat in ${wheatYears.join(", ")}.` : ": corn or soybean every year, no winter wheat."),
    el("p", { class: "step-hint" }, "→ This field's rotation now: ", el("strong", {}, name(ro.current))));
  // step 2: soil protection
  const s2 = step(2, "Measure how well each rotation protects the soil",
    "Share of spring days (15 Apr – 15 Jun) with bare soil, when heavy rain washes soil away. Lower is better.",
    bars(cands.map((c) => [c.key, c.spring_bare_share, 1]), (v) => pct(v)));
  // step 3: weather
  const sOdds = storm ? Math.round(100 * storm.share) : null;
  const s3 = step(3, "Weigh next season's weather",
    storm ? `${sOdds} in 100 possible springs next season bring a heavy storm, but a storm only hurts where the soil is bare. ` +
            "Adding frost, heat and drought risk for each crop gives the total weather risk per 100 crop-years. Lower is better."
          : "Weather risk per 100 crop-years for each rotation. Lower is better.",
    bars(cands.map((c) => [c.key, c.climate_risk_total, Math.max(...cands.map((x) => x.climate_risk_total))]), (v) => Math.round(v)));
  const s4 = step(4, "You choose what matters",
    "Soil, weather, nutrients, simplicity: farmers weigh them differently, so FieldSense doesn't hide one fixed score.",
    el("p", { class: "step-hint" }, "↓ Try the sliders below"));
  $("steps4").replaceChildren(s1, s2, s3, s4);

  // sliders
  const draw = () => {
    const ranked = scoreRotations(cands);
    $("ranking").replaceChildren(...ranked.map((r, i) => {
      const bar = el("div", { class: "rk-bar" }, el("span"));
      bar.firstChild.style.width = `${Math.max(2, 100 * r.score)}%`;
      return el("div", { class: `rk-row ${i === 0 ? "win" : ""}` }, el("div", { class: "rk-pos" }, String(i + 1)),
        el("div", { class: "rk-name" }, name(r.key), r.key === ro.current ? el("span", { class: "tag" }, "NOW") : ""), bar);
    }));
    const win = ranked[0].key;
    const share = ro.robustness_best_share && ro.robustness_best_share[win];
    $("verdict").replaceChildren("With these priorities, ", el("strong", {}, name(win)), " comes out best",
      win === ro.current ? " (what this field does now)." : ".",
      share != null ? ` It wins under ${pct(share)} of 2,000 random priority mixes.` : "");
  };
  $("sliders").replaceChildren(...PRIORITIES.map((pr) => {
    const input = el("input", { type: "range", min: "0", max: "100", value: String(weights[pr.key]), "aria-label": pr.label });
    const out = el("span", { class: "sl-val" }, String(weights[pr.key]));
    input.oninput = () => { weights[pr.key] = +input.value; out.textContent = input.value; draw(); };
    return el("label", { class: "slider" }, el("span", { class: "sl-label" }, pr.label), input, out);
  }));
  draw();
  show("decide-section");
}

// ---------- Watch a year: two fields side by side, day by day
const profileCache = {};
async function getProfile(file) {
  if (!profileCache[file]) profileCache[file] = (await fetch(DATA + file)).json();
  return profileCache[file];
}

function phaseOf(vals, d, label) {
  const v = vals[d];
  if (v == null) return ["No clear view", "clouds or snow", "none"];
  let prev = null;
  for (let k = d - 7; k >= Math.max(0, d - 21); k--) if (vals[k] != null) { prev = vals[k]; break; }
  const peakSoFar = Math.max(0, ...vals.slice(0, d + 1).filter((x) => x != null));
  const offSeason = d < 135 || d > 273;
  const wheat = label && label.startsWith("winter wheat");
  if (v < 0.3) return peakSoFar >= 0.5 && d > 180 ? ["Bare after harvest", "soil exposed until next crop", "bare"] : ["Bare soil", "nothing growing, soil exposed", "bare"];
  if (v >= 0.5) {
    if (wheat && d < 200) return ["Winter wheat growing", "sown last fall, covering the soil early", "green"];
    if (offSeason) return ["Cover crop growing", "living roots outside the main season", "green"];
    return ["Crop growing", "full canopy", "green"];
  }
  if (prev != null && v < prev - 0.02) return [d > 180 ? "Drying down / harvest" : "Thinning", "greenness falling", "mid"];
  return ["Greening up", "new growth emerging", "mid"];
}

async function renderWatch(index) {
  const groups = [...new Set(index.fields.map((f) => f.group || "Elora trial"))];
  const pairs = [];
  for (const g of groups) {
    const fs = index.fields.filter((f) => (f.group || "Elora trial") === g);
    const s = fs.find((f) => f.rotation_design === "simple"), d = fs.find((f) => f.rotation_design === "diverse");
    if (s && d) pairs.push({ label: `${g}: ${s.name.replace("Elora rotation ", "").replace(/^plot/, "Plot")} vs ${d.name.replace("Elora rotation ", "").replace(/^plot/, "Plot")}`, files: [s.file, d.file] });
  }
  // optional: every clear satellite picture of two farm fields through one year (Lesson 9, Step 2c)
  let tl = null;
  try { tl = await (await fetch(DATA + "timeline.json")).json(); } catch (e) { tl = null; }
  if (tl && tl.fields) {
    const s = tl.fields.find((f) => f.design === "simple" && f.frames.length);
    const d = tl.fields.find((f) => f.design === "diverse" && f.frames.length);
    if (s && d) pairs.unshift({ label: `Nearby farms (satellite pictures): ${s.name} vs ${d.name}`, files: [s.file, d.file], year: tl.year });
  }
  if (!pairs.length) return;
  let picMode = "green";
  const picBox = $("watch-pic");
  picBox.querySelectorAll("button").forEach((b) => (b.onclick = () => {
    picMode = b.dataset.mode;
    picBox.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    paint();
  }));
  const dayOf = (iso) => { const t = new Date(iso + "T00:00:00Z"); return Math.round((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5); };
  const pairSel = $("watch-pair"), yearSel = $("watch-year"), playBtn = $("watch-play"), speedSel = $("watch-speed");
  pairSel.replaceChildren(...pairs.map((p, i) => el("option", { value: String(i) }, p.label)));
  let profs = [], day = 0, timer = null, panels = [];

  const stop = () => { if (timer) clearInterval(timer); timer = null; playBtn.textContent = day >= 364 ? "↺ Replay" : "▶ Play"; };
  const build = () => {
    const year = +yearSel.value;
    const pics = !!(tl && year === tl.year && pairs[+pairSel.value].year);
    picBox.hidden = !pics;
    $("watch-lede").textContent = pics
      ? "A simple and a diverse farm field side by side, through one year of real NASA satellite pictures (every clear day)."
      : "A simple and a diverse field side by side, day by day, coloured by their real greenness from NASA satellites.";
    panels = profs.map((p) => {
      const bc = p.barcode, r = bc.years.indexOf(year);
      const vals = r >= 0 ? bc.values[r].map((v) => (v == null ? null : v / bc.scale)) : new Array(365).fill(null);
      const h = (p.history || []).find((x) => x.year === year);
      const tf = tl && year === tl.year ? tl.fields.find((t) => t.file === p.file) : null;
      const frames = tf ? tf.frames.map((fr) => ({ ...fr, d: dayOf(fr.date) })) : null;
      const tile = el("div", { class: frames && frames.length ? `w-tile pic${tl.view === "context" ? " ctx" : ""}` : "w-tile" });
      let img = null, shot = null;
      if (frames && frames.length) { img = el("img", { alt: "" }); shot = el("span", { class: "w-shot" }); tile.append(img, shot); }
      const phase = el("div", { class: "w-phase" }), sub = el("div", { class: "w-sub" });
      const bare = el("strong"), greenN = el("strong");
      const W = 300, H = 70;
      const curve = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "w-curve" });
      let path = "", pen = false;
      vals.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        const x = (i / 364) * W, y = H - 4 - Math.max(0, Math.min(1, v)) * (H - 8);
        path += `${pen ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`; pen = true;
      });
      curve.append(svg("line", { x1: 0, x2: W, y1: H - 4 - 0.3 * (H - 8), y2: H - 4 - 0.3 * (H - 8), stroke: "var(--line)", "stroke-dasharray": "3 3" }));
      curve.append(svg("path", { d: path, fill: "none", stroke: "var(--accent)", "stroke-width": 2 }));
      const dot = svg("circle", { r: 4.5, fill: "var(--ink)" });
      curve.append(dot);
      const f = p.field, design = f.rotation_design;
      const card = el("div", { class: `w-card ${design}` },
        el("div", { class: "w-head" }, el("strong", {}, f.name.replace("Elora rotation ", "").replace(/^plot/, "Plot")), " ",
          el("span", { class: `design ${design}` }, design)),
        el("div", { class: "w-crop" }, h ? shortCrop(h.satellite_says) : ""),
        tile, phase, sub, curve,
        el("div", { class: "w-count" }, el("span", {}, "Bare days so far: ", bare), el("span", {}, "Green days: ", greenN)));
      return { frames, img, shot, vals, label: h && h.satellite_says, tile, phase, sub, dot, bare, greenN, card, W, H };
    });
    $("watch-grid").replaceChildren(...panels.map((x) => x.card));
    paint();
  };
  const near = (vals, d) => { for (let k = d; k >= Math.max(0, d - 10); k--) if (vals[k] != null) return vals[k]; return null; };
  const caption = () => {
    const [s, d] = panels;
    if (!s || !d) return ["", false];
    const vs = near(s.vals, day), vd = near(d.vals, day);
    const storm = day >= 104 && day <= 165;
    $("watch-storm").hidden = !storm;
    if (vs == null || vd == null) return ["No clear satellite view of one of the fields around this date.", false];
    const sBare = vs < 0.3, dBare = vd < 0.3;
    if (sBare && !dBare) {
      if (storm) return ["Spring storm season: the simple field's soil is bare, the diverse field is covered.", true];
      if (day >= 240) return ["After harvest: the simple field stays bare until spring, the diverse field is green again.", true];
      if (day < 104) return ["Early spring: the diverse field already has living cover, the simple field is bare.", true];
      return ["The simple field is bare, the diverse field is covered.", true];
    }
    if (sBare && dBare) return [storm ? "Spring storm season: both fields are bare right now." : "Both fields are bare.", false];
    if (!sBare && dBare) return ["The diverse field is between crops now; the simple field is growing.", false];
    return ["Both fields are growing.", false];
  };
  const paint = () => {
    $("watch-date").textContent = doyToDate(day + 1);
    const [cap, diff] = caption();
    const capEl = $("watch-caption");
    if (capEl.textContent !== cap) capEl.textContent = cap;
    capEl.className = diff ? "watch-caption diff" : "watch-caption";
    const stormNow = day >= 104 && day <= 165;
    for (const x of panels) {
      const v = x.vals[day];
      if (x.img) {
        let fr = null;
        for (const c of x.frames) { if (c.d <= day) fr = c; else break; }
        fr = fr || x.frames[0];
        const src = fr[picMode].startsWith("data:") ? fr[picMode] : asset(fr[picMode]);
        if (x.img.getAttribute("src") !== src) x.img.setAttribute("src", src);
        x.shot.textContent = `satellite picture of ${doyToDate(fr.d + 1)}`;
      } else x.tile.style.background = v == null ? "var(--none)" : green(v);
      const [ph, sub, kind] = phaseOf(x.vals, day, x.label);
      x.phase.textContent = ph; x.sub.textContent = sub; x.phase.className = `w-phase ${kind}`;
      const upto = x.vals.slice(59, day + 1);
      x.bare.textContent = String(upto.filter((u) => u != null && u < 0.3).length);
      x.bare.className = stormNow && x.vals[day] != null && x.vals[day] < 0.3 ? "storm" : "";
      x.greenN.textContent = String(upto.filter((u) => u != null && u >= 0.4).length);
      const y = v == null ? x.H - 4 : x.H - 4 - Math.max(0, Math.min(1, v)) * (x.H - 8);
      x.dot.setAttribute("cx", ((day / 364) * x.W).toFixed(1)); x.dot.setAttribute("cy", y.toFixed(1));
      x.dot.setAttribute("opacity", v == null ? 0.25 : 1);
    }
  };
  const loadPair = async () => {
    stop();
    const pair = pairs[+pairSel.value];
    profs = await Promise.all(pair.files.map(async (f) => ({ ...(await getProfile(f)), file: f })));
    const years = profs.map((p) => new Set(p.barcode.years)).reduce((a, b) => new Set([...a].filter((y) => b.has(y))));
    const list = [...years].sort();
    const prevYear = +yearSel.value;
    yearSel.replaceChildren(...list.map((y) => el("option", { value: String(y) }, String(y))));
    const want = pair.year && list.includes(pair.year) ? pair.year : list.includes(prevYear) ? prevYear : list.includes(2023) ? 2023 : list[list.length - 1];
    yearSel.value = String(want);
    day = 59; build();
  };
  playBtn.onclick = () => {
    if (timer) { stop(); return; }
    if (day >= 364) day = 59;
    playBtn.textContent = "❚❚ Pause";
    timer = setInterval(() => { day += 1; paint(); if (day >= 364) stop(); }, +speedSel.value);
  };
  speedSel.onchange = () => { if (timer) { stop(); playBtn.click(); } };
  pairSel.onchange = loadPair;
  yearSel.onchange = () => { stop(); day = 59; build(); };
  await loadPair();
  show("watch-section");
}

function renderPassport() {
  const lg = $("legend");
  lg.replaceChildren(...Object.entries(LABEL_TEXT).map(([k, v]) => el("span", {}, badge(k), " ", v)));
  const pp = $("passport");
  pp.replaceChildren();
  const order = { measured: 0, validated: 1, modelled: 2, assumed: 3 };
  Object.values(evidence).sort((a, b) => order[a.label] - order[b.label]).forEach((e) => {
    const card = el("div", { class: `ev ${e.label}` }, badge(e.label), el("p", { class: "claim" }, nice(e.claim)));
    card.append(el("p", { class: "meta" }, "Source: ", e.source));
    if (e.test) card.append(el("p", { class: "meta" }, "Test: ", e.test));
    if (e.result) card.append(el("p", { class: "meta" }, "Result: ", nice(e.result)));
    if (e.caveat) card.append(el("p", { class: "meta" }, "Caveat: ", nice(e.caveat)));
    pp.append(card);
  });
  show("passport-section");
}

async function renderSpace() {
  let meta;
  try { meta = await (await fetch(DATA + "space.json")).json(); } catch (e) { return; }
  if (!meta) return;
  const fmtDate = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("en-CA", { month: "short", day: "numeric", timeZone: "UTC" });
  const hasPlots = meta.plots && meta.plots.rows && meta.plots.rows.length;
  const hasWide = meta.views && meta.views.length;
  if (!hasPlots && !hasWide) return;
  const draw = (mode) => {
    const grid = (table, tbl) => {
      const head = el("tr", {}, el("th", {}, ""), ...table.dates.map((d) => el("th", {}, el("strong", {}, d.label), el("br"), fmtDate(d.date))));
      const body = table.rows.map((r) => el("tr", { class: r.design },
        el("th", { class: "plot-label" }, r.name || `Plot ${r.plot}`, el("br"), el("span", { class: `design ${r.design}` }, r.design)),
        ...r.tiles.map((t, i) => el("td", {}, el("img", { src: asset(t[mode]),
          alt: `${r.name || "Plot " + r.plot} (${r.design}), ${table.dates[i].label}, ${mode === "true" ? "true colour" : "greenness"}` })))));
      tbl.replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
      tbl.classList.toggle("ctx", table.view === "context");
    };
    if (hasPlots) grid(meta.plots, $("plotgrid"));
    if (meta.farms && meta.farms.rows && meta.farms.rows.length) { grid(meta.farms, $("farmgrid")); $("farmgrid-wrap").hidden = false; }
    if (hasWide) {
      $("space-grid").replaceChildren(...meta.views.map((v) => el("figure", { class: "space-tile" },
        el("img", { src: asset(v[mode]), alt: `${v.label}, ${mode === "true" ? "true colour" : "greenness"}` }),
        el("figcaption", {}, el("strong", {}, v.label), ` · ${fmtDate(v.date)}`))));
    }
    document.querySelectorAll(".space-toggle button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.mode === mode ? "true" : "false"));
  };
  document.querySelectorAll(".space-toggle button").forEach((b) => { b.onclick = () => draw(b.dataset.mode); });
  draw("true");
  const dates = hasPlots ? meta.plots.dates : meta.views;
  const year = dates[0].date.slice(0, 4);
  const hasFarms = !!(meta.farms && meta.farms.rows && meta.farms.rows.length);
  if (hasFarms) {
    $("space-title").textContent = "Farm fields, seen from space";
    $("space-lede").textContent = `Simple and diverse farm fields near Elora on clear days in ${meta.farms.dates[0].date.slice(0, 4)}, each in its surroundings. Watch the fall: simple fields are bare, diverse fields are still green. Grey means cloud.`;
    $("plots-summary").textContent = "The Elora trial plots (small: each plot is only a few 30 m pixels)";
  } else {
    $("space-lede").textContent = hasPlots
      ? `Each square is one plot on a clear day in ${year}. Watch October: the simple plots are bare, the diverse plots are still green. Grey means cloud.`
      : `A ${meta.size_km} × ${meta.size_km} km square around the Elora Research Station through ${year}. Grey means cloud.`;
    $("plots-details").open = true;
  }
  if (!hasPlots) { $("plots-details").hidden = true; }
  if (hasWide && hasPlots) $("wide-details").hidden = false;
  if (hasWide && !hasPlots) { const d = $("wide-details"); d.hidden = false; d.open = true; }
  const note = hasFarms ? meta.farms.note : hasPlots ? meta.plots.note : "";
  $("space-note").replaceChildren(meta.source || "NASA HLS", " ", badge("measured"), note ? ` · ${note}` : "");
  show("space-section");
}

function renderHighlights(list) {
  if (!list || !list.length) return;
  $("highlights").replaceChildren(...list.map((h) => el("div", { class: "hl" },
    el("div", { class: "hl-big" }, ...(h.simple != null && h.diverse != null
      ? [el("span", { class: "c-simple", title: "simple rotation" }, `${h.simple}%`), el("span", { class: "hl-vs" }, " vs "),
         el("span", { class: "c-diverse", title: "diverse rotation" }, `${h.diverse}%`)]
      : [h.big])), el("div", { class: "hl-label" }, h.label),
    el("div", { class: "hl-note" }, h.note, " ", badge(h.evidence)))));
}

function renderGaps(p) {
  if (!p.gaps || !p.gaps.length) return;
  $("gaps").replaceChildren(...p.gaps.map((g) => el("li", {}, g)));
  show("gaps-section");
}



// =================================================================== across Canada
const CLASS_SHORT = { "winter cereal": "W", "spring crop": "Sp", "summer crop": "Su", forage: "F", fallow: "Fa" };
function miniBarcode(bc, width = 300) {
  const rows = bc.years.length, rh = 9, c = el("canvas", { width: String(width), height: String(rows * rh), class: "mini-bc",
    role: "img", "aria-label": `greenness every day, ${bc.years[0]}–${bc.years[rows - 1]}` });
  const g = c.getContext("2d");
  bc.values.forEach((row, r) => row.forEach((v, d) => {
    g.fillStyle = v == null ? "rgba(128,128,128,.18)" : green(v / bc.scale);
    g.fillRect(Math.floor((d * width) / 365), r * rh, Math.ceil(width / 365) + 1, rh - 1);
  }));
  return c;
}

function climateBox(c) {
  if (!c) return "";
  const st = c.station, cor = c.correction || {}, sm = c.summary || {};
  const stLine = st ? `Nearest Environment Canada station with a long record: ${st.name} (${st.km} km away). ` : "No usable station nearby: NASA POWER uncorrected. ";
  const fix = [];
  if (cor.rain) fix.push(`rain error on held-out years ${cor.rain.held_out_error_raw_pct}% → ${cor.rain.held_out_error_corrected_pct}%`);
  if (cor.temperature) fix.push(`night temperature bias ${cor.temperature.bias_raw_c} → ${cor.temperature.bias_corrected_c} °C`);
  const risks = Object.values(c.odds.risks).sort((a, b) => b.share - a.share);
  return el("div", { class: "rd-climate" },
    el("h4", {}, `Next season (${c.odds.target_year}) weather here`),
    el("p", { class: "rd-sub" }, stLine, fix.length ? `Correction: ${fix.join("; ")}. ` : "", badge(c.evidence)),
    el("p", { class: "rd-sum" }, `Typical year (${c.years[0]}–${c.years[1]}): ${Math.round(sm.annual_precip_mm)} mm of rain, ${Math.round(sm.gdd10_may_sep)} growing degree-days, ${Math.round(sm.frost_free_days)} frost-free days. Warming ${c.trend.c_per_decade} °C per decade (90% interval ${c.trend.low} to ${c.trend.high}).`),
    el("div", { class: "rd-odds" }, ...risks.map((k) => el("div", { class: "rd-odd" },
      el("div", { class: "rd-bar" }, el("span", { style: `width:${Math.round(100 * k.share)}%` })),
      el("strong", {}, `${Math.round(100 * k.share)} in 100`), el("span", {}, nice(k.text)),
      el("small", {}, ` (${k.past_years} past years)`)))),
    el("p", { class: "rd-note" }, "Risk thresholds are rules of thumb for Ontario corn, soybean and wheat ", badge("assumed"),
      ". Thresholds and rotation options for each province's own crops are the next step."));
}

async function renderCanada() {
  let data;
  try { data = await (await fetch(DATA + "canada.json")).json(); } catch (e) { console.info("No canada.json:", e); return; }
  if (!data || !data.regions || !data.regions.length) return;
  try { drawCanada(data); } catch (err) {
    console.error(err);
    show("canada-section");
    $("canada-headline").textContent = `The Canada results could not be drawn (${err.message}). Please report this.`;
  }
}

function drawCanada(data) {
  const P = (v) => (v == null ? "–" : `${Math.round(100 * v)}%`);
  const pair = (c) => el("span", { class: "sd" }, el("span", { class: "c-simple" }, P(c.simple)), " / ", el("span", { class: "c-diverse" }, P(c.diverse)));
  const diffTxt = (d) => (d ? `${d.diff > 0 ? "+" : ""}${Math.round(100 * d.diff)} pts (${Math.round(100 * d.lo)} to ${Math.round(100 * d.hi)})` : "too few fields");

  // map: southern Canada as a soft band, provinces as dashed lines, a pin per region
  const map = $("canada-map");
  const X = (lon) => 40 + ((lon + 120) / 50) * 920, Y = (lat) => 30 + ((55 - lat) / 13) * 210;
  map.append(svg("path", { d: "M14 40 C 260 18, 560 26, 986 52 L 986 288 C 760 296, 640 270, 560 262 C 400 250, 200 252, 14 258 Z", class: "cm-land" }));
  for (const [lon, name] of [[-120, "BC"], [-110, "AB"], [-102, "SK"], [-95.2, "MB"], [-79.5, "ON"], [-64, "QC"]]) {
    if (name !== "BC" && name !== "QC") map.append(svg("line", { x1: X(lon), y1: 20, x2: X(lon), y2: 275, class: "cm-border" }));
  }
  const detail = $("region-detail");
  const pins = {};
  const select = (key) => {
    const r = data.regions.find((x) => x.region === key);
    Object.entries(pins).forEach(([k, g]) => g.classList.toggle("on", k === key));
    document.querySelectorAll("#canada-table tbody tr").forEach((tr) => tr.classList.toggle("on", tr.dataset.region === key));
    const t = r.timing;
    detail.replaceChildren(
      el("div", { class: "rd-head" }, el("h3", {}, `${r.name} · ${r.place}`), el("p", { class: "rd-sub" }, `Main crops: ${r.system}. Crop timing read correctly in ${t.agree} of ${t.checked} field-years `, badge(t.evidence === "validated" ? "validated" : "modelled"))),
      climateBox(r.climate),
      el("div", { class: "rd-fields" }, ...r.fields.map((f) => {
        const yrs = Object.keys(f.crops).map(Number).filter((y) => y >= f.barcode.years[0]).sort();
        return el("div", { class: `rd-field ${f.group}` },
          el("div", { class: "rd-name" }, f.name, el("span", { class: `design ${f.group}` }, f.group)),
          el("div", { class: "rd-crops" }, yrs.map((y) => f.crops[y]).join(" → ")),
          miniBarcode(f.barcode),
          el("div", { class: "rd-years" }, el("span", {}, "Jan"), el("span", {}, `${f.barcode.years[0]}–${f.barcode.years[f.barcode.years.length - 1]}, one row per year`), el("span", {}, "Dec")),
          el("div", { class: "rd-nums" }, `Bare ${P(f.cover.bare_share_season)} of the season · green outside summer ${P(f.cover.green_share_off_season)}`));
      })));
  };
  for (const r of data.regions) {
    const g = svg("g", { class: `cm-pin ${r.timing.evidence === "validated" ? "ok" : ""}${r.custom ? " custom" : ""}`, tabindex: "0", role: "button", "aria-label": r.name });
    const x = X(r.lon), y = Y(r.lat);
    g.append(svg("circle", { cx: x, cy: y, r: 16, class: "cm-halo" }), svg("circle", { cx: x, cy: y, r: 8, class: "cm-dot" }));
    const t1 = svg("text", { x, y: y - 26, "text-anchor": "middle", class: "cm-label" }); t1.textContent = r.name;
    const t2 = svg("text", { x, y: y + 36, "text-anchor": "middle", class: "cm-sub" }); t2.textContent = `${r.n_simple + r.n_diverse} fields`;
    g.append(t1, t2);
    g.onclick = () => select(r.region);
    g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(r.region); } };
    pins[r.region] = g;
    map.append(g);
  }

  // scorecard
  const head = el("tr", {}, el("th", {}, "Region"), el("th", {}, "Fields", el("br"), el("small", {}, "simple / diverse")),
    el("th", {}, "Crop timing", el("br"), el("small", {}, "vs crop map")),
    el("th", {}, "Bare days in season", el("br"), el("small", {}, "simple / diverse")),
    el("th", {}, "Bare in spring storms", el("br"), el("small", {}, "simple / diverse")),
    el("th", {}, "Green outside summer", el("br"), el("small", {}, "simple / diverse")),
    el("th", {}, "Diverse − simple, bare days", el("br"), el("small", {}, "90% interval")));
  const body = data.regions.map((r) => {
    const tr = el("tr", { "data-region": r.region },
      el("th", {}, r.name),
      el("td", {}, `${r.n_simple} / ${r.n_diverse}`),
      el("td", {}, r.timing.checked ? `${Math.round(100 * r.timing.share)}% ` : "–", r.timing.checked ? el("small", {}, `(${r.timing.agree}/${r.timing.checked})`) : ""),
      el("td", {}, pair(r.cover.bare_share_season)),
      el("td", {}, pair(r.cover.spring_bare_share)),
      el("td", {}, pair(r.cover.green_share_off_season)),
      el("td", {}, diffTxt(r.cover.bare_share_season.diff)));
    tr.onclick = () => select(r.region);
    return tr;
  });
  $("canada-table").replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));

  const a = data.all, d = a && a.cover.bare_share_season.diff;
  if (d) {
    const fewer = -Math.round(100 * d.diff);
    $("canada-headline").replaceChildren(
      el("strong", {}, fewer > 0 ? `Across ${data.regions.length} provinces, diverse rotations leave the soil bare ${fewer} points less of the season` : `Across ${data.regions.length} provinces, no clear difference in bare days`),
      ` (90% interval ${-Math.round(100 * d.hi)} to ${-Math.round(100 * d.lo)} points, ${a.n_simple} simple vs ${a.n_diverse} diverse fields). Crop timing read correctly in ${a.timing.agree} of ${a.timing.checked} field-years.`);
  }
  $("canada-rule").replaceChildren(data.source, " ", badge("measured"), ` · ${data.rule} Intervals resample fields, so few fields give wide intervals.`);
  select((data.regions.find((r) => r.region === "on") || data.regions[0]).region);
  show("canada-section");
}

// =================================================================== landing layer
// Aerial-looking patchwork of fields, drawn (not a photo), used behind the hero and the numbers band.
function drawFields(canvas, seed = 7) {
  if (!canvas) return;
  const draw = () => {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const c = canvas.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    let r = seed;
    const rnd = () => ((r = (r * 16807) % 2147483647) / 2147483647);
    const COLS = ["#3f7d3a", "#5a9444", "#7aa84f", "#9cb860", "#c2c27a", "#b9a066", "#8f7650", "#4d8a46", "#6c9a3f", "#a8b86a"];
    c.fillStyle = "#4b7d40"; c.fillRect(0, 0, w, h);
    c.save();
    c.translate(w / 2, h / 2); c.rotate(-0.33);
    const span = Math.hypot(w, h);
    let x = -span / 2;
    while (x < span / 2) {
      const colW = 90 + rnd() * 170;
      let y = -span / 2;
      while (y < span / 2) {
        const fh = 60 + rnd() * 220;
        const col = COLS[Math.floor(rnd() * COLS.length)];
        c.fillStyle = col; c.fillRect(x, y, colW - 3, fh - 3);
        c.strokeStyle = "rgba(255,255,255,.08)"; c.lineWidth = 1;          // crop rows
        const vertical = rnd() < 0.5, step = 4 + rnd() * 3;
        c.beginPath();
        if (vertical) for (let k = x + step; k < x + colW - 3; k += step) { c.moveTo(k, y); c.lineTo(k, y + fh - 3); }
        else for (let k = y + step; k < y + fh - 3; k += step) { c.moveTo(x, k); c.lineTo(x + colW - 3, k); }
        c.stroke();
        if (rnd() < 0.18) { c.fillStyle = "rgba(25,60,30,.55)"; c.fillRect(x - 2, y + fh - 6, colW + 2, 6); }   // hedgerow
        y += fh;
      }
      x += colW;
    }
    c.restore();
    c.strokeStyle = "rgba(230,225,200,.35)"; c.lineWidth = 3;           // a country road
    c.beginPath(); c.moveTo(-20, h * 0.85); c.bezierCurveTo(w * 0.3, h * 0.55, w * 0.6, h * 0.95, w + 20, h * 0.35); c.stroke();
  };
  draw();
  let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 150); });
}

function typeLoop(node, phrases) {
  if (!node) return;
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) { node.textContent = phrases[0]; return; }
  let i = 0, n = phrases[0].length, deleting = false;
  const tick = () => {
    const p = phrases[i];
    node.textContent = p.slice(0, n);
    let wait = deleting ? 35 : 70;
    if (!deleting && n === p.length) { deleting = true; wait = 1800; }
    else if (deleting && n === 0) { deleting = false; i = (i + 1) % phrases.length; wait = 300; }
    else n += deleting ? -1 : 1;
    setTimeout(tick, wait);
  };
  setTimeout(tick, 1800);
}

function revealOnScroll() {
  const items = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) { items.forEach((x) => x.classList.add("in")); return; }
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.15 });
  items.forEach((x, k) => { x.style.transitionDelay = `${(k % 4) * 90}ms`; io.observe(x); });
  setTimeout(() => items.forEach((x) => x.classList.add("in")), 2500);     // never leave content hidden
}

function countUp(node, to, decimals = 0) {
  const fmt = (v) => v.toLocaleString("en-CA", { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) { node.textContent = fmt(to); return; }
  const t0 = performance.now(), dur = 1400;
  const step = (t) => { const k = Math.min(1, (t - t0) / dur); node.textContent = fmt(to * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

// share of crop-years read correctly, from an evidence result like "... 8 of 8 ...; ... 53 of 58 ..."
function accuracyFrom(id) {
  const e = evidence[id];
  if (!e || !e.result) return null;
  const pairs = [...e.result.matchAll(/(\d+) of (\d+)/g)].map((m) => [+m[1], +m[2]]);
  if (!pairs.length) return null;
  const ok = pairs.reduce((a, p) => a + p[0], 0), all = pairs.reduce((a, p) => a + p[1], 0);
  return all ? Math.round((100 * ok) / all) : null;
}

async function renderStats(index) {
  const farms = index.fields.filter((f) => (f.group || "") === "Nearby farms").length;
  let years = null;
  try { years = (await getProfile(index.fields[0].file)).barcode.years.length; } catch (e) { years = null; }
  const accFarms = accuracyFrom("hls_crop_history_farms"), accTrial = accuracyFrom("hls_crop_history");
  const cards = [
    years && [years, "", "years of satellite pictures per field"],
    [1000, "", "possible next seasons simulated"],
    farms ? [farms, "", "nearby farm fields tested"] : [index.fields.length, "", "trial plots read from space"],
    accFarms != null ? [accFarms, "%", "of farm crop-years read correctly vs. Canada's crop map"]
      : accTrial != null ? [accTrial, "%", "of trial crop-years read correctly vs. field records"] : null,
  ].filter(Boolean);
  const nodes = cards.map(([v, unit, lab]) => {
    const num = el("span", {}, "0");
    const card = el("div", { class: "stat-card" }, el("div", { class: "num" }, num, unit ? el("small", {}, unit) : ""), el("div", { class: "lab" }, lab));
    return { card, num, v };
  });
  $("stat-cards").replaceChildren(...nodes.map((x) => x.card));
  const go = () => nodes.forEach((x) => countUp(x.num, x.v));
  if (!("IntersectionObserver" in window)) return go();
  const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { go(); io.disconnect(); } }, { threshold: 0.3 });
  io.observe($("stat-cards"));
}

// The tablet in the hero: a simple and a diverse field playing through one year, on a loop.
async function renderDevice(index) {
  const box = $("dev-tiles"), dateEl = $("dev-date"), bar = $("dev-progress");
  const still = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const dayOf = (iso) => { const t = new Date(iso + "T00:00:00Z"); return Math.round((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5); };
  let tiles = [], year = null;
  let tl = null;
  try { tl = await (await fetch(DATA + "timeline.json")).json(); } catch (e) { tl = null; }
  const pick = (list, key) => ["simple", "diverse"].map((d) => list.find((x) => x[key] === d)).filter(Boolean);
  if (tl && tl.fields) {
    const pair = pick(tl.fields.filter((f) => f.frames && f.frames.length), "design");
    if (pair.length === 2) {
      year = tl.year;
      tiles = pair.map((f) => ({ design: f.design, name: f.name, frames: f.frames.map((x) => ({ ...x, d: dayOf(x.date) })) }));
    }
  }
  if (!tiles.length) {                                   // fall back: colour from each field's greenness
    const farms = index.fields.filter((f) => f.group === "Nearby farms");
    const pair = pick(farms.length ? farms : index.fields, "rotation_design");
    if (pair.length < 2) return;
    const profs = await Promise.all(pair.map((f) => getProfile(f.file)));
    const common = profs[0].barcode.years.filter((y) => profs[1].barcode.years.includes(y));
    year = common.includes(2023) ? 2023 : common[common.length - 1];
    tiles = profs.map((p, k) => {
      const bc = p.barcode, r = bc.years.indexOf(year);
      return { design: pair[k].rotation_design, name: pair[k].name.replace("Elora rotation ", "").replace(/^plot/, "Plot"),
        vals: bc.values[r].map((v) => (v == null ? null : v / bc.scale)) };
    });
  }
  const ctx = !!(tl && tl.view === "context");
  const parts = tiles.map((t) => {
    const img = t.frames ? el("img", { alt: "" }) : null, sw = t.frames ? null : el("div", { class: "swatch" }), cap = el("em");
    box.append(el("div", { class: `dev-tile ${t.design}${ctx ? " ctx" : ""}` }, el("b", {}, t.design), img || sw, cap));
    return { t, img, sw, cap };
  });
  let day = 60, last = {};
  const paint = () => {
    dateEl.textContent = `${doyToDate(day + 1)} ${year}`;
    bar.style.width = `${((day - 60) / (330 - 60)) * 100}%`;
    for (const p of parts) {
      if (p.img) {
        let fr = p.t.frames[0];
        for (const c of p.t.frames) { if (c.d <= day) fr = c; else break; }
        const src = fr.green.startsWith("data:") ? fr.green : asset(fr.green);
        if (last[p.t.name] !== src) { p.img.src = src; last[p.t.name] = src; }
        p.cap.textContent = p.t.name;
      } else {
        let v = null;
        for (let k = day; k >= Math.max(0, day - 20) && v == null; k--) v = p.t.vals[k];
        p.sw.style.background = v == null ? "#24342b" : green(v);
        p.cap.textContent = p.t.name;
      }
    }
  };
  if (still) { day = 200; paint(); return; }
  paint();
  setInterval(() => { day = day >= 330 ? 60 : day + 2; paint(); }, 55);
}

function renderLanding() {
  drawFields($("hero-fields"), 7);
  drawFields($("stats-fields"), 31);
  typeLoop($("hero-type"), ["Protect your soil", "Plan for 2027 weather", "Choose your next crop", "Keep roots in the ground"]);
  revealOnScroll();
}
renderLanding();

// ---------- load
async function loadField(entry, buttons) {
  buttons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.file === entry.file ? "true" : "false"));
  const p = await (await fetch(DATA + entry.file)).json();
  renderGlance(p); renderBarcode(p); renderCoverChart(p); renderOdds(p); renderDecide(p); renderRotations(p); renderExplanations(p); renderGaps(p);
  history.replaceState(null, "", `#${entry.file.replace(".json", "")}`);
}

async function main() {
  try {
    const index = await (await fetch(DATA + "index.json")).json();
    try {
      const ev = await (await fetch(DATA + "evidence.json")).json();
      evidence = Object.fromEntries(ev.evidence.map((e) => [e.id, e]));
    } catch (e) { evidence = {}; }
    const tabs = $("plot-tabs");
    let lastGroup = null;
    const buttons = index.fields.map((f) => {
      const group = f.group || "Elora trial";
      if (group !== lastGroup && index.fields.some((x) => (x.group || "Elora trial") !== group)) {
        tabs.append(el("span", { class: "tab-group" }, group));
        lastGroup = group;
      }
      const b = el("button", { type: "button", "data-file": f.file }, f.name.replace("Elora rotation ", "").replace(/^plot/, "Plot"),
        el("small", {}, f.rotation_design ? ` · ${f.rotation_design}` : ""));
      b.classList.add(f.rotation_design === "diverse" ? "is-diverse" : "is-simple");
      b.onclick = () => loadField(f, buttons);
      tabs.append(b);
      return b;
    });
    const wanted = location.hash.slice(1) + ".json";
    const first = index.fields.find((f) => f.file === wanted) || index.fields[0];
    await loadField(first, buttons);
    renderPassport();
    renderFigures(index.figures);
    renderHighlights(index.highlights);
    renderSpace();
    renderWatch(index);
    renderCanada();
    renderDevice(index);
    renderStats(index);
    $("loading").remove();
  } catch (err) {
    $("loading").textContent = "No field data found yet. Export the data with fieldsense.export.export_demo and add the files to docs/data/. " +
      "(If you opened this file directly from your computer, serve it instead: python -m http.server)";
    console.error(err);
  }
}
main();

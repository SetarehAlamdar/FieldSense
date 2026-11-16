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
    day = 59;
    if (tl && want === tl.year && pair.year) {                 // start where both fields have a clear picture
      const firsts = tl.fields.filter((f) => f.frames.length).map((f) => dayOf(f.frames[0].date));
      if (firsts.length) day = Math.min(200, Math.max(59, ...firsts));
    }
    build();
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

// Key moments for soil, from the "Watch a year" pictures (timeline.json): the clear picture
// closest to each date, for the simple and the diverse field, labelled from measured greenness.
const MOMENTS = [["Spring storm season", 130], ["Early summer", 172], ["Late summer", 227], ["After harvest", 295]];
async function loadMoments() {
  let tl;
  try { tl = await (await fetch(DATA + "timeline.json")).json(); } catch (e) { return null; }
  if (!tl || tl.view !== "context") return null;
  const pair = ["simple", "diverse"].map((d) => tl.fields.find((f) => f.design === d && f.frames.length));
  if (pair.some((f) => !f)) return null;
  const doy = (iso) => { const t = new Date(iso + "T00:00:00Z"); return Math.round((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5) + 1; };
  const rows = [];
  for (const f of pair) {
    let vals = null;
    try {
      const bc = (await getProfile(f.file)).barcode, r = bc.years.indexOf(tl.year);
      if (r >= 0) vals = bc.values[r].map((v) => (v == null ? null : v / bc.scale));
    } catch (e) { vals = null; }
    const cells = MOMENTS.map(([, target]) => {
      let best = null;
      for (const fr of f.frames) {
        const d = doy(fr.date);
        if (Math.abs(d - target) <= 25 && (!best || Math.abs(d - target) < Math.abs(best.d - target))) best = { ...fr, d };
      }
      if (!best) return null;
      let v = null;
      if (vals) for (let k = best.d - 1; k >= Math.max(0, best.d - 8) && v == null; k--) v = vals[k];
      best.state = v == null ? "" : v < 0.3 ? "bare soil" : v < 0.5 ? "partly green" : "growing";
      return best;
    });
    rows.push({ name: f.name, design: f.design, cells });
  }
  return { year: tl.year, rows };
}

async function renderSpace() {
  let meta;
  try { meta = await (await fetch(DATA + "space.json")).json(); } catch (e) { return; }
  if (!meta) return;
  const moments = await loadMoments();
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
    if (moments) {
      const head = el("tr", {}, el("th", {}, ""), ...MOMENTS.map(([label]) => el("th", {}, el("strong", {}, label))));
      const body = moments.rows.map((r) => el("tr", { class: r.design },
        el("th", { class: "plot-label" }, r.name, el("br"), el("span", { class: `design ${r.design}` }, r.design)),
        ...r.cells.map((c) => el("td", {}, c
          ? el("figure", { class: "moment" }, el("img", { src: c[mode].startsWith("data:") ? c[mode] : asset(c[mode]), alt: `${r.name} (${r.design}), ${doyToDate(c.d)}` }),
              el("figcaption", {}, el("span", { class: `state ${c.state.replace(" ", "-")}` }, c.state), ` ${doyToDate(c.d)}`))
          : el("span", { class: "no-view" }, "no clear view")))));
      $("momentgrid").replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
    }
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
  if (moments) {                                       // the farm grid becomes a fold-out under the key moments
    $("farms-slot").append($("farmgrid-wrap"));
    $("moments-wrap").hidden = false;
    $("farms-details").hidden = !(meta.farms && meta.farms.rows && meta.farms.rows.length);
    if (meta.farms) $("farms-summary").textContent = `More farm fields, on four fixed dates in ${meta.farms.dates[0].date.slice(0, 4)}`;
  }
  draw(moments ? "green" : "true");
  const dates = hasPlots ? meta.plots.dates : meta.views;
  const year = dates[0].date.slice(0, 4);
  const hasFarms = !!(meta.farms && meta.farms.rows && meta.farms.rows.length);
  if (moments) {
    const [sr, dr] = moments.rows;
    $("space-title").textContent = "Simple vs diverse, seen from space";
    $("space-lede").textContent = `${sr.name} (simple) and ${dr.name} (diverse) in ${moments.year}, the year with the biggest measured difference in soil cover. Four moments that matter for the soil, each the clearest picture near that date. Brown means bare soil, green means growing plants.`;
    $("plots-summary").textContent = "The Elora trial plots (small: each plot is only a few 30 m pixels)";
  } else if (hasFarms) {
    $("space-title").textContent = "Farm fields, seen from space";
    $("space-lede").textContent = `Simple and diverse farm fields near Elora on four clear days in ${meta.farms.dates[0].date.slice(0, 4)}, each in its surroundings. One year shows one crop: the rotation difference shows over several years (see each field's barcode below). Grey means cloud.`;
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
  const cor = c.correction || {}, sm = c.summary || {};
  const risks = Object.values(c.odds.risks).sort((a, b) => b.share - a.share);
  const fix = [];
  if (cor.rain) fix.push(`rain error on held-out years ${cor.rain.held_out_error_raw_pct}% → ${cor.rain.held_out_error_corrected_pct}%`);
  if (cor.temperature) fix.push(`night temperature bias ${cor.temperature.bias_raw_c} → ${cor.temperature.bias_corrected_c} °C`);
  const short = (t) => nice(t).replace(/ \(.*\)$/, "");
  return el("div", { class: "rd-climate" },
    el("h4", {}, `2027 weather here: the three biggest risks `, badge(c.evidence)),
    el("div", { class: "rd-top3" }, ...risks.slice(0, 3).map((k) => el("div", { class: "rd-risk" },
      el("strong", {}, `${Math.round(100 * k.share)}`), el("small", {}, " in 100"), el("span", {}, short(k.text))))),
    el("details", { class: "more rd-more" }, el("summary", {}, "More about the weather"),
      el("p", {}, fix.length ? `NASA POWER corrected with the station: ${fix.join("; ")}. ` : "No usable station nearby: NASA POWER uncorrected. ",
        `Typical year (${c.years[0]}–${c.years[1]}): ${Math.round(sm.annual_precip_mm)} mm of rain, ${Math.round(sm.gdd10_may_sep)} growing degree-days, ${Math.round(sm.frost_free_days)} frost-free days. Warming ${c.trend.c_per_decade} °C per decade (90% interval ${c.trend.low} to ${c.trend.high}).`),
      el("ul", {}, ...risks.map((k) => el("li", {}, `${Math.round(100 * k.share)} in 100: ${nice(k.text)} (${k.past_years} past years)`))),
      el("p", { class: "rd-note" }, "Risk thresholds are rules of thumb for Ontario corn, soybean and wheat ", badge("assumed"),
        ". Thresholds and rotation options for each province's own crops are the next step.")));
}

// "Try your own field": checks the location, names the nearest measured location, and
// sends the farmer to the My Field notebook (the full analysis needs NASA login and ~15 min).
function myFieldPanel(regions, select) {
  const km = (a, b, c, d) => {
    const r = Math.PI / 180, x = Math.sin(((c - a) * r) / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(((d - b) * r) / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(x));
  };
  const APP = "https://setarehalamdar-fieldsense.hf.space/";
  let marker = null, map = null;
  const setPoint = (lat, lon) => {
    $("mf-go").href = `${APP}?loc=${lat.toFixed(5)},${lon.toFixed(5)}`;
    $("mf-go").textContent = "Read this field in the FieldSense app →";
    if (map) {
      if (marker) marker.setLatLng([lat, lon]);
      else marker = L.circleMarker([lat, lon], { radius: 9, color: "#fff", weight: 3, fillColor: "#e2a33a", fillOpacity: 1 }).addTo(map);
    }
  };
  if (typeof L !== "undefined" && $("mf-map")) {
    map = L.map("mf-map", { scrollWheelZoom: false }).setView([50.5, -98], 4);
    // Satellite background: Esri World Imagery; if its tiles fail, switch to Sentinel-2 cloudless (EOX, keyless)
    const esri = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics" });
    const s2 = L.tileLayer("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg", {
      maxZoom: 17, attribution: '<a href="https://s2maps.eu">Sentinel-2 cloudless</a> by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2020)' });
    let failed = 0, loaded = 0;
    const toS2 = () => { if (map.hasLayer(esri)) { map.removeLayer(esri); s2.addTo(map); } };
    esri.on("tileload", () => { loaded++; });
    esri.on("tileerror", () => { if (++failed >= 3 && loaded === 0) toS2(); });
    esri.addTo(map);
    setTimeout(() => { if (loaded === 0) toS2(); }, 6000);
    for (const r of regions) L.circleMarker([r.lat, r.lon], { radius: 6, color: "#3b3f99", fillColor: "#5aa58f", fillOpacity: 0.9, weight: 2 })
      .bindTooltip(`${r.name}: measured`).addTo(map);
    map.on("click", (e) => {
      $("mf-loc").value = `${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;
      $("mf-form").requestSubmit ? $("mf-form").requestSubmit() : $("mf-form").onsubmit(new Event("submit"));
    });
    setTimeout(() => map.invalidateSize(), 300);                // the section was hidden while the map was built
    if ("IntersectionObserver" in window) new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && map.invalidateSize())).observe($("mf-map"));
  } else if ($("mf-map")) {
    $("mf-map").closest(".mf-map-box").hidden = true;          // no internet for the map library: typing still works
  }
  $("mf-form").onsubmit = (e) => {
    e.preventDefault();
    const out = $("mf-out");
    const m = $("mf-loc").value.match(/(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)/);
    if (!m) { out.textContent = "Please paste two numbers: latitude, longitude (for example 50.45, -104.61)."; return; }
    const lat = +m[1], lon = +m[2];
    if (!(lat > 41.5 && lat < 60 && lon > -141 && lon < -52)) { out.textContent = "That point isn't in Canada's farmland (latitude 42–60, longitude −141 to −52)."; return; }
    setPoint(lat, lon);
    if (map && map.getZoom() < 13) map.setView([lat, lon], 14);
    const near = regions.map((r) => ({ r, d: km(lat, lon, r.lat, r.lon) })).sort((a, b) => a.d - b.d)[0];
    out.replaceChildren(`Point ${lat.toFixed(4)}, ${lon.toFixed(4)}. Closest location FieldSense has measured: `,
      el("button", { type: "button", class: "linkish" }, `${near.r.name} (${near.r.place})`), `, ${Math.round(near.d)} km away. `,
      "Check the pin is in the middle of your field, then open the app: it starts reading right away.");
    out.querySelector(".linkish").onclick = () => { select(near.r.region); $("region-detail").scrollIntoView({ behavior: "smooth", block: "start" }); };
    if (navigator.clipboard) navigator.clipboard.writeText(`${lat}, ${lon}`).then(() => out.append(" (Copied to your clipboard.)"), () => {});
  };
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
    const st = r.climate && r.climate.station;
    const chip = (txt, cls = "") => el("span", { class: `rd-chip ${cls}` }, txt);
    detail.replaceChildren(
      el("div", { class: "rd-head" }, el("h3", {}, `${r.name} · ${r.place}`),
        el("div", { class: "rd-chips" },
          chip(`${r.n_simple + r.n_diverse} fields: ${r.n_simple} simple · ${r.n_diverse} diverse`),
          chip(`Crop reading ${Math.round(100 * (t.share || 0))}% right ${t.evidence === "validated" ? "✓" : ""}`, t.evidence === "validated" ? "ok" : ""),
          st ? chip(`Station: ${st.name}, ${st.km} km`) : chip("No station: weather uncorrected"))),
      climateBox(r.climate),
      el("div", { class: "rd-fields" }, ...r.fields.map((f) => {
        const yrs = Object.keys(f.crops).map(Number).filter((y) => y >= f.barcode.years[0]).sort();
        const bc = miniBarcode(f.barcode);
        bc.setAttribute("title", yrs.map((y) => `${y}: ${f.crops[y]}`).join("\n"));
        return el("div", { class: `rd-field ${f.group}` },
          el("div", { class: "rd-name" }, r.region === "on" ? f.name.replace("Ontario field", "Farm field") : f.name,
            el("span", { class: `design ${f.group}` }, f.group)),
          bc,
          el("div", { class: "rd-nums" }, el("span", { class: "c-simple" }, `bare ${P(f.cover.bare_share_season)}`), " · ",
            el("span", { class: "c-diverse" }, `green off-season ${P(f.cover.green_share_off_season)}`)));
      })),
      el("p", { class: "rd-foot" }, `Each card: one field, ${r.fields[0] ? r.fields[0].barcode.years[0] : ""}–2025, one row per year, January to December (brown = bare, green = growing). Hover a barcode for its crops.`));
  };
  const placed = [];                                    // pins already drawn, to keep labels apart
  for (const r of [...data.regions].sort((a, b) => !!a.custom - !!b.custom)) {   // regions first, own places last
    const x0 = X(r.lon), y0 = Y(r.lat);
    const near = placed.find((p) => Math.abs(p.x - x0) < 100 && Math.abs(p.y - y0) < 60);
    placed.push({ x: x0, y: y0, key: r.region });
    const g = svg("g", { class: `cm-pin ${r.timing.evidence === "validated" ? "ok" : ""}${r.custom ? " custom" : ""}`, tabindex: "0", role: "button", "aria-label": r.name });
    const x = X(r.lon), y = Y(r.lat);
    g.append(svg("circle", { cx: x, cy: y, r: 16, class: "cm-halo" }), svg("circle", { cx: x, cy: y, r: 8, class: "cm-dot" }));
    const n = `${r.n_simple + r.n_diverse} fields`;
    if (near) {
      // crowded: this pin's name and count go together below it; the neighbour's count moves to its right
      const t = svg("text", { x, y: y + 40, "text-anchor": "middle", class: "cm-label small" });
      t.textContent = r.name;
      const t2 = svg("text", { x, y: y + 58, "text-anchor": "middle", class: "cm-sub" }); t2.textContent = n;
      g.append(t, t2);
      const other = pins[near.key] && pins[near.key].querySelector(".cm-sub");
      if (other) { other.setAttribute("x", near.x + 22); other.setAttribute("y", near.y + 5); other.setAttribute("text-anchor", "start"); }
    } else {
      const t1 = svg("text", { x, y: y - 26, "text-anchor": "middle", class: "cm-label" }); t1.textContent = r.name;
      const t2 = svg("text", { x, y: y + 36, "text-anchor": "middle", class: "cm-sub" }); t2.textContent = n;
      g.append(t1, t2);
    }
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
    const provs = data.regions.filter((r) => !r.custom).length, where = data.regions.length > provs
      ? `${data.regions.length} locations in ${provs} provinces` : `${provs} provinces`;
    const lower = data.regions.filter((r) => ((r.cover || {}).bare_share_season || {}).diff && r.cover.bare_share_season.diff.diff < 0);
    const clear = data.regions.filter((r) => ((r.cover || {}).bare_share_season || {}).diff && r.cover.bare_share_season.diff.hi < 0).map((r) => r.name);
    const each = lower.length === data.regions.length
      ? ` Diverse fields were less bare in all ${data.regions.length} locations; the difference is clear on its own in ${clear.length ? clear.join(" and ") : "none of them"}, `
        + `and elsewhere it is small enough to be chance with only 6–8 fields per location.`
      : ` Diverse fields were less bare in ${lower.length} of ${data.regions.length} locations.`;
    $("canada-headline").replaceChildren(
      el("strong", {}, fewer > 0 ? `Across ${where}, diverse rotations leave the soil bare about ${-Math.round(SEASON_DAYS * d.diff)} fewer days a season` : `Across ${where}, no clear difference in bare days`),
      ` (March to November: ${fewer} points less of the season, 90% interval ${-Math.round(100 * d.hi)} to ${-Math.round(100 * d.lo)} points, ${a.n_simple} simple vs ${a.n_diverse} diverse fields).${each} `
      + `These are farms, not an experiment: the Elora trial is the test where the rotation is the only difference. `
      + `Crop timing agreed with Canada's crop map in ${a.timing.agree} of ${a.timing.checked} field-years.`);
  }
  $("canada-rule").replaceChildren(data.source, " ", badge("measured"), ` · ${data.rule} Intervals resample fields, so few fields give wide intervals.`);
  select((data.regions.find((r) => r.region === "on") || data.regions[0]).region);
  myFieldPanel(data.regions, select);
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

const SEASON_DAYS = 275;   // 1 Mar - 30 Nov, the season of canada.cover_numbers

async function renderStats(index) {
  const farms = index.fields.filter((f) => (f.group || "") === "Nearby farms").length;
  let years = null;
  try { years = (await getProfile(index.fields[0].file)).barcode.years.length; } catch (e) { years = null; }
  const accFarms = accuracyFrom("hls_crop_history_farms"), accTrial = accuracyFrom("hls_crop_history");
  let ca = null;
  try { ca = await (await fetch(DATA + "canada.json")).json(); } catch (e) { ca = null; }
  if (ca && ca.all && ca.all.timing && ca.all.timing.checked) {
    const nf = ca.all.n_simple + ca.all.n_diverse, prov = ca.regions.filter((r) => !r.custom).length;
    const t = ca.all.timing, d = ca.all.cover.bare_share_season.diff;
    $("stats-title").textContent = `Proven on a 10-year rotation experiment. Checked on ${nf} farm fields in ${prov} provinces.`;
    $("stats-text").textContent = "At the Elora Research Station, both rotations grow side by side on the same land. Over 10 years, "
      + "the diverse one kept living cover on 39% of off-season days, the simple one on 3%. "
      + `Then FieldSense read ${nf} farm fields it had never seen, from Alberta to Quebec, and checked itself against Canada's crop map.`
      + (d && d.diff < 0 ? ` Real farms show the same pattern: diverse fields were bare about ${-Math.round(SEASON_DAYS * d.diff)} fewer days a season (March to November).` : "");
    const cardsCa = [
      [nf, "", "farm fields tested across Canada"],
      [prov, "", "provinces, each checked on its own"],
      [Math.round((100 * t.agree) / t.checked), "%", `of crop-years agree with Canada's crop map (${t.agree}/${t.checked})`],
      [1000, "", "possible 2027 seasons per location"],
    ];
    return countCards(cardsCa);
  }
  const cards = [
    years && [years, "", "years of satellite pictures per field"],
    [1000, "", "possible next seasons simulated"],
    farms ? [farms, "", "nearby farm fields tested"] : [index.fields.length, "", "trial plots read from space"],
    accFarms != null ? [accFarms, "%", "of farm crop-years agree with Canada's crop map"]
      : accTrial != null ? [accTrial, "%", "of trial crop-years match the field records"] : null,
  ].filter(Boolean);
  return countCards(cards);
}

function countCards(cards) {
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


// ---------- The farmer's question: a satellite passes, and the field's barcode fills in, stripe by stripe.
// An illustration of how FieldSense works (not real data): a simple and a diverse field through a typical year.
function farmerScene() {
  const box = $("story-scene");
  if (!box) return;
  const NS = "http://www.w3.org/2000/svg";
  const STATES = {
    s: { field: "var(--snow)", cell: null }, c: { field: null, cell: null },
    b: { field: "#a77b4f", cell: "#9a6a3a" }, l: { field: "#9fd08f", cell: "#8fc98a" },
    g: { field: "#3f8a4a", cell: "#2f6b34" }, h: { field: "#d4b25e", cell: "#c9a04a" },
  };
  const ROWS = [
    { name: "Simple rotation", seq: "scsssbbcbblggcgghhbbbcss",
      text: "Simple rotation (corn, soybean): the soil stays bare from spring until June, and again after harvest." },
    { name: "Diverse rotation", seq: "scssslgcgggghlgcgggllcss",
      text: "Diverse rotation (winter wheat, then clover): green in spring and again after harvest. Same satellites, a very different barcode." },
  ];
  const END = "Two fields, two barcodes (an illustration of a typical year). FieldSense reads the real barcode of any field in Canada from every clear NASA satellite pass.";
  const X0 = 128, CW = 15.5, CH = 17, RY = [356, 382];
  const cells = [], months = "JFMAMJJASOND";
  let svg = `<svg viewBox="0 0 520 430" role="img" aria-label="Illustration: a farmer stands by a field while a satellite passes overhead; each clear pass adds one stripe to the field's barcode">
    <rect class="sc-sky" x="0" y="0" width="520" height="250"/>
    <rect class="sc-sky2" x="0" y="170" width="520" height="80" opacity=".7"/>
    <g fill="#fff" opacity=".75"><ellipse cx="80" cy="120" rx="26" ry="9"/><ellipse cx="98" cy="113" rx="16" ry="9"/><ellipse cx="430" cy="140" rx="24" ry="8"/><ellipse cx="446" cy="134" rx="14" ry="8"/></g>
    <path class="sc-orbit" d="M-40 78 Q 260 -20 560 78"/>
    <path class="sc-hill" d="M0 236 C 90 206 170 214 250 230 C 330 212 430 206 520 230 L520 250 L0 250 Z"/>
    <rect class="sc-ground" x="0" y="240" width="520" height="100"/>
    <polygon id="sc-beam" points="0,0 0,0 0,0" fill="#ffe08a" opacity="0"/>
    <polygon id="sc-field" points="200,248 460,248 498,326 160,326" fill="#a77b4f"/>
    <g stroke="rgba(0,0,0,.13)" stroke-width="2">${Array.from({ length: 9 }, (_, i) => {
      const a = 200 + (i + 1) * 26, b = 160 + (i + 1) * 33.8; return `<line x1="${a}" y1="248" x2="${b}" y2="326"/>`; }).join("")}</g>
    <g id="sc-cloud" opacity="0"><ellipse cx="330" cy="168" rx="46" ry="15" fill="#fff"/><ellipse cx="306" cy="160" rx="24" ry="14" fill="#fff"/><ellipse cx="350" cy="156" rx="28" ry="17" fill="#fff"/><ellipse cx="330" cy="172" rx="50" ry="10" fill="#e8edf3"/></g>
    <g id="sc-sat">
      <rect x="-25" y="-5" width="16" height="10" rx="1.5" fill="#3b63b5"/><rect x="9" y="-5" width="16" height="10" rx="1.5" fill="#3b63b5"/>
      <path d="M-21 -5v10M-17 -5v10M-13 -5v10M13 -5v10M17 -5v10M21 -5v10" stroke="#8fb0ea" stroke-width="1"/>
      <path d="M-9 0h4M5 0h4" stroke="#9aa0b5" stroke-width="2"/>
      <rect x="-6" y="-7" width="12" height="14" rx="2" fill="#d9dbe4" stroke="#9aa0b5"/><circle cx="0" cy="9" r="2.4" fill="#5aa58f"/>
    </g>
    <g id="sc-farmer">
      <rect x="83" y="292" width="10" height="36" rx="3" fill="#34508a"/><rect x="97" y="292" width="10" height="36" rx="3" fill="#34508a"/>
      <rect x="80" y="324" width="15" height="7" rx="3" fill="#5a3b22"/><rect x="96" y="324" width="15" height="7" rx="3" fill="#5a3b22"/>
      <rect x="77" y="248" width="36" height="50" rx="10" fill="#b8443a"/>
      <path d="M77 262h36M77 276h36M90 248v50M101 248v50" stroke="#8e2f28" stroke-width="2" opacity=".6"/>
      <rect x="69" y="252" width="10" height="34" rx="5" fill="#b8443a"/><circle cx="74" cy="288" r="5" fill="#e0a982"/>
      <g id="sc-arm"><rect x="111" y="252" width="10" height="34" rx="5" fill="#b8443a"/><circle cx="116" cy="288" r="5" fill="#e0a982"/></g>
      <rect x="90" y="240" width="10" height="10" fill="#e0a982"/>
      <circle cx="95" cy="228" r="15" fill="#e6b48f"/>
      <path d="M80 224 a15 13 0 0 1 30 0 z" fill="#3f8a74"/><path d="M104 223 h16 a3 3 0 0 1 0 5 h-16 z" fill="#2f6b5a"/>
      <circle cx="100" cy="230" r="1.8" fill="#2a2a35"/><circle cx="108" cy="230" r="1.8" fill="#2a2a35"/>
      <path d="M99 236 q5 4 10 0" stroke="#a8524a" stroke-width="1.8" fill="none" stroke-linecap="round"/>
    </g>`;
  ROWS.forEach((r, i) => {
    svg += `<text class="sc-label" x="${X0 - 8}" y="${RY[i] + 12}" text-anchor="end">${r.name}</text>`;
    for (let k = 0; k < 24; k++) svg += `<rect id="sc-c${i}-${k}" x="${X0 + k * CW}" y="${RY[i]}" width="${CW - 1.5}" height="${CH}" rx="2" fill="none" stroke="var(--line)"/>`;
  });
  for (let m = 0; m < 12; m++) svg += `<text class="sc-axis" x="${X0 + (2 * m + 1) * CW - 0.75}" y="${RY[1] + CH + 13}" text-anchor="middle">${months[m]}</text>`;
  svg += `<g font-size="9.5" font-family="Inter, system-ui, sans-serif" fill="var(--muted)">
    <rect x="${X0}" y="${RY[1] + CH + 21}" width="9" height="9" rx="2" fill="#9a6a3a"/><text x="${X0 + 13}" y="${RY[1] + CH + 29}">bare soil</text>
    <rect x="${X0 + 72}" y="${RY[1] + CH + 21}" width="9" height="9" rx="2" fill="#2f6b34"/><text x="${X0 + 85}" y="${RY[1] + CH + 29}">growing</text>
    <rect x="${X0 + 140}" y="${RY[1] + CH + 21}" width="9" height="9" rx="2" fill="#c9a04a"/><text x="${X0 + 153}" y="${RY[1] + CH + 29}">ripe</text>
    <rect x="${X0 + 190}" y="${RY[1] + CH + 21}" width="9" height="9" rx="2" class="sc-none"/><text x="${X0 + 203}" y="${RY[1] + CH + 29}">no clear view (cloud, snow)</text></g></svg>`;
  box.innerHTML = svg;
  const q = (id) => box.querySelector("#" + id);
  const field = q("sc-field"), beam = q("sc-beam"), sat = q("sc-sat"), cloud = q("sc-cloud"), arm = q("sc-arm"), cap = $("scene-caption");
  const pos = (t) => [(1 - t) ** 2 * -40 + 2 * (1 - t) * t * 260 + t * t * 560, (1 - t) ** 2 * 78 + 2 * (1 - t) * t * -20 + t * t * 78];
  const paintCell = (row, k) => {
    const st = STATES[ROWS[row].seq[k]], c = q(`sc-c${row}-${k}`);
    c.removeAttribute("stroke");
    if (st.cell) c.setAttribute("fill", st.cell); else { c.removeAttribute("fill"); c.setAttribute("class", "sc-none"); }
    if (st.field) field.setAttribute("fill", st.field);
  };
  const clearRows = () => box.querySelectorAll("[id^=sc-c]").forEach((c) => { c.removeAttribute("class"); c.setAttribute("fill", "none"); c.setAttribute("stroke", "var(--line)"); });
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    ROWS.forEach((_, i) => { for (let k = 0; k < 24; k++) paintCell(i, k); });
    field.setAttribute("fill", STATES.g.field);
    const [x, y] = pos(0.5); sat.setAttribute("transform", `translate(${x} ${y})`);
    cap.textContent = END;
    return;
  }
  const PASS = 1000, ROW_PAUSE = 1600, END_PAUSE = 4200;
  let row = 0, k = 0, t0 = null, painted = false, pauseUntil = 0, visible = true, last = 0;
  cap.textContent = ROWS[0].text;
  if ("IntersectionObserver" in window) new IntersectionObserver((es) => { visible = es.some((e) => e.isIntersecting); }, { threshold: 0.1 }).observe(box);
  const frame = (now) => {
    requestAnimationFrame(frame);
    if (!visible) { if (t0 !== null) t0 += now - last; if (pauseUntil) pauseUntil += now - last; last = now; return; }
    last = now;
    if (pauseUntil) {
      if (now < pauseUntil) return;
      pauseUntil = 0; t0 = now;
      if (row >= ROWS.length) { row = 0; clearRows(); }
      cap.textContent = ROWS[row].text;
    }
    if (t0 === null) t0 = now;
    const t = Math.min(1, (now - t0) / PASS), [x, y] = pos(t);
    sat.setAttribute("transform", `translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${((t - 0.5) * 24).toFixed(1)})`);
    const ch = ROWS[row].seq[k], cloudy = ch === "c";
    const on = t > 0.36 && t < 0.64, a = on ? Math.sin(((t - 0.36) / 0.28) * Math.PI) : 0;
    const bottom = cloudy ? 160 : 248, left = cloudy ? 296 : 200, right = cloudy ? 364 : 460;
    beam.setAttribute("points", `${x.toFixed(1)},${(y + 8).toFixed(1)} ${left},${bottom} ${right},${bottom}`);
    beam.setAttribute("opacity", (0.45 * a).toFixed(2));
    cloud.setAttribute("opacity", cloudy ? Math.min(1, Math.sin(t * Math.PI) * 1.6).toFixed(2) : "0");
    arm.setAttribute("transform", `rotate(${(-150 * a).toFixed(1)} 116 256)`);
    if (!painted && t >= 0.5) { paintCell(row, k); painted = true; }
    if (t >= 1) {
      painted = false; t0 = now; k += 1;
      if (k >= 24) { k = 0; row += 1; pauseUntil = now + (row >= ROWS.length ? END_PAUSE : ROW_PAUSE); if (row >= ROWS.length) cap.textContent = END; }
    }
  };
  requestAnimationFrame(frame);
}

// Question cards: jump to the answer, just below the sticky menu, and correct once late content has loaded.
function questionJumps() {
  document.querySelectorAll(".q-card").forEach((a) => a.addEventListener("click", (e) => {
    let target = document.querySelector(a.getAttribute("href"));
    if ((!target || target.hidden) && a.dataset.fallback) target = document.querySelector(a.dataset.fallback);
    if (!target || target.hidden) return;
    e.preventDefault();
    const off = () => { const nav = document.querySelector(".site-nav"); return (nav ? nav.getBoundingClientRect().height : 64) + 12; };
    const go = (smooth) => window.scrollTo({ top: window.scrollY + target.getBoundingClientRect().top - off(), behavior: smooth ? "smooth" : "auto" });
    go(true);
    [900, 1800].forEach((ms) => setTimeout(() => { if (Math.abs(target.getBoundingClientRect().top - off()) > 24) go(false); }, ms));
  }));
}

function renderLanding() {
  drawFields($("hero-fields"), 7);
  drawFields($("stats-fields"), 31);
  farmerScene();
  questionJumps();
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

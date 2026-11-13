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
  "CS": "Corn – soybean",
  "CS+rye": "Corn – soybean + rye",
  "SWC": "Soybean – wheat – corn",
  "SWC+clover": "Soybean – wheat + clover – corn",
};

let evidence = {};

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
  if (ro.next_crop_2026) stat("In 2026", ro.next_crop_2026.split(" (")[0], ro.next_crop_2026.includes("(") ? "satellite can't tell which; ask the farmer" : "next in the cycle", evLabel("hls_crop_history"));
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
  $("barcode-evidence").replaceChildren("Greenness ", badge("measured"), " from NASA HLS satellite pixels inside the field. Crop labels on the right ",
    badge(evLabel("hls_crop_history") || "modelled"), evidence.hls_crop_history && evidence.hls_crop_history.result ? `: ${evidence.hls_crop_history.result}.` : ".");
  show("barcode-section");
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
  ["climate_risk_total", "2026 risk-hits /100 crop-years", -1, (v) => Math.round(v)],
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
    COLS.forEach(([k, , , fmt]) => tr.append(el("td", { class: c[k] === best[k] ? "best" : "" }, String(fmt(c[k])))));
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
  $("not-included").replaceChildren(`Not included yet: ${(ro.not_included || []).join(", ")}. Leaving out costs makes diverse rotations look better than many farmers would find them. Soil cover for rotations the field hasn't tried comes from a crop-calendar model `,
    badge(ro.calendar_model_evidence || "modelled"), ".");
  show("rotation-section");
}

const PARTS = [["what", "What it is"], ["soil_cover", "Soil cover"], ["climate_2026", "Climate in 2026"],
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

function renderPassport() {
  const lg = $("legend");
  lg.replaceChildren(...Object.entries(LABEL_TEXT).map(([k, v]) => el("span", {}, badge(k), " ", v)));
  const pp = $("passport");
  pp.replaceChildren();
  const order = { measured: 0, validated: 1, modelled: 2, assumed: 3 };
  Object.values(evidence).sort((a, b) => order[a.label] - order[b.label]).forEach((e) => {
    const card = el("div", { class: `ev ${e.label}` }, badge(e.label), el("p", { class: "claim" }, e.claim));
    card.append(el("p", { class: "meta" }, "Source: ", e.source));
    if (e.test) card.append(el("p", { class: "meta" }, "Test: ", e.test));
    if (e.result) card.append(el("p", { class: "meta" }, "Result: ", e.result));
    if (e.caveat) card.append(el("p", { class: "meta" }, "Caveat: ", e.caveat));
    pp.append(card);
  });
  show("passport-section");
}

function renderGaps(p) {
  if (!p.gaps || !p.gaps.length) return;
  $("gaps").replaceChildren(...p.gaps.map((g) => el("li", {}, g)));
  show("gaps-section");
}

// ---------- load
async function loadField(entry, buttons) {
  buttons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.file === entry.file ? "true" : "false"));
  const p = await (await fetch(DATA + entry.file)).json();
  renderGlance(p); renderBarcode(p); renderOdds(p); renderRotations(p); renderExplanations(p); renderGaps(p);
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
    const buttons = index.fields.map((f) => {
      const b = el("button", { type: "button", "data-file": f.file }, f.name.replace("Elora rotation ", "").replace(/^plot/, "Plot"),
        el("small", {}, f.rotation_design ? ` · ${f.rotation_design}` : ""));
      b.onclick = () => loadField(f, buttons);
      tabs.append(b);
      return b;
    });
    const wanted = location.hash.slice(1) + ".json";
    const first = index.fields.find((f) => f.file === wanted) || index.fields[0];
    await loadField(first, buttons);
    renderPassport();
    $("loading").remove();
  } catch (err) {
    $("loading").textContent = "No field data found yet. Run the Lesson 9 export and upload the files to docs/data/. " +
      "(If you opened this file directly from your computer, serve it instead: python -m http.server)";
    console.error(err);
  }
}
main();

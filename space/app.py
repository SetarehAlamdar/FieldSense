"""FieldSense: your field, anywhere in Canada (Hugging Face Space).

A visitor types a location. The app finds the field at that point on Canada's crop map, reads
every clear NASA HLS image of it (2023-2025), corrects NASA POWER weather with the nearest
Environment Canada station, and shows the field's history, soil cover, 2027 weather odds and
which rotation and why. The Space owner's NASA Earthdata login is a Space secret
(EARTHDATA_USERNAME, EARTHDATA_PASSWORD); visitors never log in. Nothing is stored or published.
"""
import os
import re
import threading

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
import gradio as gr
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

CACHE = os.environ.get("FIELDSENSE_CACHE", "/tmp/fieldsense")
os.makedirs(CACHE, exist_ok=True)
START = os.environ.get("FIELDSENSE_START", "2023-01-01")      # 3 years keeps a run to ~5-10 minutes
_login_lock, _logged_in = threading.Lock(), [False]


def nasa_login():
    with _login_lock:
        if not _logged_in[0]:
            import earthaccess
            from fieldsense.sources import hls
            earthaccess.login(strategy="environment")
            hls.use_earthaccess_login()
            _logged_in[0] = True


def parse_location(text):
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)", text or "")
    if not m:
        raise ValueError("Please paste two numbers: latitude, longitude (for example 50.45, -104.61).")
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (41.5 < lat < 60 and -141 < lon < -52):
        raise ValueError("That point isn't in Canada's farmland (latitude 42 to 60, longitude -141 to -52).")
    return lat, lon


CMAP = LinearSegmentedColormap.from_list(
    "g", [(0, "#8c5a2b"), (0.25, "#d9c48c"), (0.5, "#c9dd8a"), (0.75, "#5aa040"), (1, "#1f6b2a")])
CMAP.set_bad("#e2e4e8")


def barcode_figure(rec, crops):
    bc = rec["barcode"]
    vals = np.array([[np.nan if v is None else v / 100 for v in r] for r in bc["values"]])
    fig, ax = plt.subplots(figsize=(9, 0.8 + 0.5 * len(bc["years"])))
    ax.imshow(np.ma.masked_invalid(vals), aspect="auto", cmap=CMAP, vmin=0.1, vmax=0.9, interpolation="nearest")
    ax.set_yticks(range(len(bc["years"])))
    ax.set_yticklabels([f"{y}  {crops.get(y, '')}" for y in bc["years"]])
    ax.set_xticks([0, 59, 120, 181, 243, 304])
    ax.set_xticklabels(["Jan", "Mar", "May", "Jul", "Sep", "Nov"])
    ax.set_title("Your field, every day: brown = bare soil, green = growing, grey = no clear view", fontsize=10)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.tight_layout()
    return fig


def history_md(field, rec):
    c = rec["cover"]
    ok = sum(x["agree"] for x in rec["check"])
    lines = [f"### Your field: {field['area_ha']} ha",
             f"Rotation type: **{field['group'] or 'not a simple or diverse rotation (e.g. permanent grass)'}**",
             "", "| Year | Crop (crop map) | Satellite reads |", "|---|---|---|"]
    seen = {x["year"]: x for x in rec["check"]}
    for y in sorted(field["crops"]):
        s = seen.get(y)
        lines.append(f"| {y} | {field['crops'][y]} | {s['satellite_class'] + ('' if s['agree'] else ' (differs)') if s else '–'} |")
    lines += ["", f"**Soil cover, measured by NASA satellites:** bare **{c['bare_share_season']:.0%}** of the season "
                  f"(1 Mar–30 Nov), bare **{c['spring_bare_share']:.0%}** of spring storm season (15 Apr–15 Jun), "
                  f"green **{c['green_share_off_season']:.0%}** outside summer.",
              f"Crop reading check: the satellite agrees with the crop map in **{ok} of {len(rec['check'])}** years."]
    return "\n".join(lines)


def weather_md(clim):
    s, st, cor = clim["summary"], clim["station"], clim["correction"]
    lines = ["### Next season (2027) weather at your field"]
    lines.append(f"Nearest Environment Canada station: **{st['name']}** ({st['km']} km away)." if st
                 else "No usable station nearby: NASA POWER uncorrected (*modelled*).")
    fix = []
    if cor.get("rain"):
        fix.append(f"rain error on held-out years {cor['rain']['held_out_error_raw_pct']}% → {cor['rain']['held_out_error_corrected_pct']}%")
    if cor.get("temperature"):
        fix.append(f"night temperature bias {cor['temperature']['bias_raw_c']} → {cor['temperature']['bias_corrected_c']} °C")
    if fix:
        lines.append("NASA POWER corrected with it: " + "; ".join(fix) + ".")
    lines += [f"Typical year: {s['annual_precip_mm']:.0f} mm of rain, {s['gdd10_may_sep']:.0f} growing degree-days, "
              f"{s['frost_free_days']:.0f} frost-free days. Warming {clim['trend']['c_per_decade']} °C per decade.",
              "", "| Out of 100 possible 2027 seasons | Risk | Past 30 years |", "|---|---|---|"]
    for v in sorted(clim["odds"]["risks"].values(), key=lambda v: -v["share"]):
        lines.append(f"| **{round(100 * v['share'])}** | {v['text'].replace('degC', '°C')} | {v['past_years']} |")
    lines.append("\n*Risk thresholds are rules of thumb for corn, soybean and wheat (assumed).*")
    return "\n".join(lines)


def rotation_md(adv):
    if not adv["available"]:
        return "### Which rotation\n" + adv["reason"]
    rob = adv["robustness"]
    lines = ["### Which rotation, and why", f"Your field now: **{adv['current_name']}** (read from the satellite)."]
    if adv["keep"]:
        lines.append(f"Suggestion: **keep it**. It comes out best under {rob[adv['current_name']]:.0%} of 2,000 different priority mixes.")
    else:
        lines.append(f"Suggestion: **{adv['suggested_name']}**. It comes out best under {rob[adv['suggested_name']]:.0%} of "
                     f"2,000 different priority mixes (your current rotation: {rob.get(adv['current_name'], 0):.0%}).")
    lines.append(f"If you keep your rotation, 2027 is: {adv['next_crop_if_kept']}.")
    for k, parts in adv["why"].items():
        lines.append(f"\n**Why ({'your rotation now' if k == adv['current'] else 'the suggestion'}):**")
        lines += [f"- {p['text']} *[{p['evidence']}]*" for p in parts.values()]
    lines.append("\n*Measured = straight from satellite or station data; validated = checked against independent records; "
                 "modelled = from a model; assumed = a rule of thumb. Yield and profit are not included.*")
    return "\n".join(lines)


def run(location):
    from fieldsense import anywhere as aw
    from fieldsense import canada as ca
    from fieldsense import myfield as mf
    from fieldsense.phenology import field_history

    empty = (None, "", "", "")
    try:
        lat, lon = parse_location(location)
    except ValueError as e:
        yield (f"**{e}**", *empty)
        return
    try:
        nasa_login()
        yield ("Finding your field on Canada's crop map…", *empty)
        field = mf.field_at_point(lon, lat, CACHE)
        if field is None:
            yield ("**No farm field found at this point.** Move the point to the middle of a field and try again.", *empty)
            return
        if not field.get("farmland", True):
            yield (f"**This point is {field['land']} on Canada's crop map, not a farm field.** "
                   "In Google Maps (Satellite view), right-click in the middle of a field and paste that location.", *empty)
            return
        yield (f"Found a {field['area_ha']} ha field. Getting next season's weather from the nearest station (1–2 minutes)…", *empty)
        clim = aw.climate_for_point(lat, lon, cache_dir=CACHE)
        yield ("Reading every clear NASA satellite image of your field since 2023 (5–10 minutes)…", None, "", weather_md(clim), "")
        tag = f"{lat:.4f}_{lon:.4f}".replace("-", "m")
        ndvi_file = os.path.join(CACHE, f"field_{tag}.csv")
        ca.hls_ndvi_for_fields({1: field["lonlat"]}, ndvi_file, start=START)
        if not os.path.exists(ndvi_file):
            yield ("**No clear satellite images found for this field.** Try again later.", None, "", weather_md(clim), "")
            return
        ndvi = pd.read_csv(ndvi_file, parse_dates=["date"])
        recs = ca.region_records(ndvi, [{"id": 1, "name": "Your field", "group": field["group"] or "other",
                                         "codes": field["codes"]}], years=range(int(START[:4]), 2026))
        if not recs:
            yield ("**Too few clear satellite views of this field.**", None, "", weather_md(clim), "")
            return
        rec = recs[0]
        hist = field_history(ndvi[ndvi["ndvi"].notna()][["date", "ndvi"]]).to_dict("records")
        adv = mf.rotation_advice(hist, clim["odds"], {"green_share_off_season": rec["cover"]["green_share_off_season"],
                                                     "spring_bare_share": rec["cover"]["spring_bare_share"]}, field["codes"])
        yield ("**Done.**", barcode_figure(rec, field["crops"]), history_md(field, rec), weather_md(clim), rotation_md(adv))
    except Exception as e:
        yield (f"**Something went wrong:** {type(e).__name__}: {str(e)[:200]}. Please try again in a minute.", *empty)


with gr.Blocks(title="FieldSense: your field", theme=gr.themes.Soft(primary_hue="teal")) as demo:
    gr.Markdown("# FieldSense: your field, anywhere in Canada\n"
                "Paste your field's location from Google Maps (right-click on the field, then click the numbers). "
                "FieldSense finds the field at that point on Canada's crop map and reads it from NASA satellites. "
                "**It takes about 5–10 minutes.** Nothing is stored or published.")
    with gr.Row():
        loc = gr.Textbox(label="Latitude, longitude", placeholder="e.g. 43.6412, -80.4180", scale=4)
        go = gr.Button("Read my field", variant="primary", scale=1)
    status = gr.Markdown()
    plot = gr.Plot(label="History from space")
    with gr.Row():
        hist = gr.Markdown()
        rot = gr.Markdown()
    wx = gr.Markdown()
    gr.Markdown("NASA HLS (Landsat + Sentinel-2) · NASA POWER · AAFC Annual Crop Inventory · Environment and Climate Change Canada. "
                "Open source: [github.com/SetarehAlamdar/FieldSense](https://github.com/SetarehAlamdar/FieldSense) · "
                "NASA Space Apps 2026, Team Star Farmer.")
    go.click(run, inputs=loc, outputs=[status, plot, hist, wx, rot])
    loc.submit(run, inputs=loc, outputs=[status, plot, hist, wx, rot])

demo.queue(default_concurrency_limit=2)

if __name__ == "__main__":
    demo.launch()

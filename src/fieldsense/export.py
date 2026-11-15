"""Export: make the PUBLIC copy of the data that the demo website reads.

The website never reads the private working data. It reads small JSON files published
next to it (docs/data/). This module builds those files and is the privacy gate:

- coordinates are rounded to 2 decimals (about 1 km): enough to say "Elora", not enough
  to locate a plot;
- plot areas and the survey-map source are dropped;
- the barcode is added as numbers (years x 365 days, greenness x 100) so the page can draw it;
- `check_public` refuses anything that still looks private;
- in the rotation table, the field's CURRENT rotation gets its satellite-measured soil cover
  (measured beats modelled), and the robustness shares are recomputed with it.
"""
import copy
import json
import os
import shutil

import numpy as np
import pandas as pd

from .phenology import barcode_matrix, daily_ndvi, measured_cover_shares
from .rotation import CRITERIA, NEXT_SEASON, next_crop, rank_robustness

PRIVATE_KEYS = {"area_ha", "location_source"}

# Figures made by the analysis that the website shows in its gallery (copied if present).
FIGURES = [
    ("living_cover_elora.png", "Living cover outside the main crop season, all four plots",
     "Share of off-season days with green plants, per year. Diverse rotations (plots 3-4) keep the soil covered far more often."),
    ("climate_indicators_elora.png", "Climate indicators, 1996-2025",
     "Frost-free days, heat units, heat at corn pollination, heavy spring rain, summer dry spells and fall warmth, from corrected NASA POWER weather."),
    ("rotation_calendars.png", "When each rotation keeps the soil green",
     "Modelled from the crop calendar: green = growing plants, brown = bare soil, one row per year of the cycle."),
]


def public_profile(profile, coord_decimals=2):
    """A copy of a field profile that is safe to publish."""
    p = copy.deepcopy(profile)
    f = p["field"]
    for k in PRIVATE_KEYS:
        f.pop(k, None)
    for k in ("lat", "lon"):
        if f.get(k) is not None:
            f[k] = round(float(f[k]), coord_decimals)
    f["location_note"] = f"Coordinates rounded to {coord_decimals} decimals (about 1 km)."
    ro = p.get("rotation_options")
    if ro and ro.get("current") and p.get("history"):
        ro["next_season"] = NEXT_SEASON                  # the next decision: the season after this year's harvest
        ro["next_crop"] = next_crop(ro["current"], p["history"], NEXT_SEASON)
    return p


def barcode_payload(obs, since=None):
    """Barcode as compact numbers: greenness x 100 as integers, null where unseen."""
    m = barcode_matrix(daily_ndvi(obs))
    if since:
        m = m[m.index >= since]
    vals = np.round(m.values.astype(float) * 100)
    rows = [[None if np.isnan(v) else int(v) for v in row] for row in vals]
    return {"years": [int(y) for y in m.index], "days": 365, "scale": 100, "values": rows}


def use_measured_cover(pub, matrix, since=2018):
    """Replace the current rotation's modelled soil cover with the satellite measurement."""
    ro = pub.get("rotation_options")
    if not ro or not ro.get("candidates"):
        return pub
    meas = measured_cover_shares(matrix, since=since)
    for c in ro["candidates"]:
        c["cover_evidence"] = "measured" if c["key"] == ro["current"] else ro.get("calendar_model_evidence", "modelled")
        if c["key"] == ro["current"]:
            for k, v in meas.items():
                if k in c and np.isfinite(v):
                    c[k] = round(float(v), 4)
            # heavy rain on bare soil depends on spring bare soil: recompute it with the measurement
            p_rain = (((pub.get("climate_odds") or {}).get("risks") or {}).get("heavy_rain_on_bare_soil") or {}).get("share")
            if p_rain is not None and "risk_heavy_rain_on_bare_soil" in c:
                new = round(100 * p_rain * c["spring_bare_share"], 1)
                c["climate_risk_total"] = round(c["climate_risk_total"] - c["risk_heavy_rain_on_bare_soil"] + new, 1)
                c["risk_heavy_rain_on_bare_soil"] = new
    table = pd.DataFrame(ro["candidates"]).set_index("key")
    crit = {k: v for k, v in CRITERIA.items() if k in table.columns}
    ro["robustness_best_share"] = {k: round(float(v), 3) for k, v in rank_robustness(table, crit).items()}
    ro["measured_since"] = since
    ro["measured_cover"] = {k: round(float(v), 4) for k, v in meas.items() if np.isfinite(v)}
    return pub


ROTATION_GROUP = {"CSS": "conventional", "CSS+rye": "conventional", "SWC": "diverse", "SWC+covers": "diverse"}


def highlights(pubs):
    """The 3-4 headline numbers for the top of the page, computed from the public profiles."""
    groups = {}
    farms = [p for p in pubs if p.get("group") == "Nearby farms"]
    pubs = [p for p in pubs if p.get("group", "Elora trial") == "Elora trial"] or pubs
    for p in pubs:
        ro = p.get("rotation_options") or {}
        g = ROTATION_GROUP.get(ro.get("current"))
        if g and ro.get("measured_cover"):
            groups.setdefault(g, []).append(ro)
    out = []
    if "conventional" in groups and "diverse" in groups:
        mean = lambda g, k: 100 * np.mean([ro["measured_cover"][k] for ro in groups[g]])
        out.append({"simple": round(mean('conventional', 'spring_bare_share')), "diverse": round(mean('diverse', 'spring_bare_share')),
                    "big": f"{mean('conventional', 'spring_bare_share'):.0f}% vs {mean('diverse', 'spring_bare_share'):.0f}%",
                    "label": "Soil left bare when spring storms hit",
                    "note": "simple vs diverse rotation, seen by satellite since 2018", "evidence": "measured"})
        out.append({"simple": round(mean('conventional', 'green_share_off_season')), "diverse": round(mean('diverse', 'green_share_off_season')),
                    "big": f"{mean('conventional', 'green_share_off_season'):.0f}% vs {mean('diverse', 'green_share_off_season'):.0f}%",
                    "label": "Living cover outside the summer season",
                    "note": "simple vs diverse: roots protecting the soil in spring and fall", "evidence": "measured"})
    risks = ((pubs[0].get("climate_odds") or {}).get("risks") or {}) if pubs else {}
    if "heavy_rain_on_bare_soil" in risks:
        r = risks["heavy_rain_on_bare_soil"]
        out.append({"big": f"{round(100 * r['share'])} in 100",
                    "label": f"Springs with a heavy storm (25 mm+), next season ({NEXT_SEASON})",
                    "note": f"from 1,000 possible seasons; it happened in {r['past_years']} past years", "evidence": "assumed"})
    fg = {}
    for p in farms:
        ro = p.get("rotation_options") or {}
        if ro.get("measured_cover"):
            fg.setdefault(p["field"].get("rotation_design"), []).append(ro["measured_cover"]["spring_bare_share"])
    if fg.get("simple") and fg.get("diverse"):
        a, b = round(100 * float(np.mean(fg["simple"]))), round(100 * float(np.mean(fg["diverse"])))
        out.append({"simple": a, "diverse": b, "big": f"{a}% vs {b}%",
                    "label": f"Same pattern on {len(fg['simple']) + len(fg['diverse'])} nearby farms",
                    "note": "soil bare in spring storms, simple vs diverse farm fields (rotation from Canada's crop map)",
                    "evidence": "measured"})
    for ro in groups.get("diverse", []):
        nxt, yr = ro.get("next_crop") or ro.get("next_crop_2026", ""), ro.get("next_season", 2026)
        if nxt and "(" not in nxt:
            out.append({"big": nxt[0].upper() + nxt[1:], "label": f"What comes next on the diverse plots ({yr})",
                        "note": "read from their 3-year cycle, seen from space", "evidence": "validated"})
            break
    return out


def check_public(obj, path="data"):
    """Problems that would make `obj` unsafe to publish (empty list = OK)."""
    problems = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in PRIVATE_KEYS:
                problems.append(f"{path}.{k}: private field")
            if k in ("lat", "lon") and isinstance(v, float) and len(repr(v).split(".")[-1]) > 2:
                problems.append(f"{path}.{k}: coordinate not rounded")
            problems += check_public(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            problems += check_public(v, f"{path}[{i}]")
    elif isinstance(obj, str) and "PRIVATE" in obj:
        problems.append(f"{path}: mentions a private file")
    return problems


def export_demo(profile_dir, hls_csv, out_dir, plot_column="plot", demo_dir=None, farm_hls_csv=None):
    """Write data/index.json, data/evidence.json and data/<field>.json for the website.

    Trial plots: profiles named plot_<n>.json, greenness in `hls_csv`.
    Nearby farms (optional): profiles named farm_<n>.json, greenness in `farm_hls_csv`.
    If `demo_dir` is given, the analysis figures listed in FIGURES are copied too
    (as fig_<name>.png) and listed in index.json for the page's gallery.
    Returns the list of files written. Raises ValueError if anything fails `check_public`.
    """
    os.makedirs(out_dir, exist_ok=True)
    sets = [("plot_", hls_csv, "Elora trial")]
    if farm_hls_csv and os.path.exists(farm_hls_csv):
        sets.append(("farm_", farm_hls_csv, "Nearby farms"))
    written, index, pubs = [], [], []
    for prefix, csv, group in sets:
        hls = pd.read_csv(csv, parse_dates=["date"])
        hls = hls[hls["ndvi"].notna()]
        for fname in sorted((f for f in os.listdir(profile_dir) if f.startswith(prefix) and f.endswith(".json")),
                            key=lambda f: int(f[len(prefix):-5])):
            with open(os.path.join(profile_dir, fname)) as fh:
                prof = json.load(fh)
            num = int(fname[len(prefix):-5])
            pub = public_profile(prof)
            obs = hls[hls[plot_column] == num][["date", "ndvi"]]
            pub["barcode"] = barcode_payload(obs)
            use_measured_cover(pub, barcode_matrix(daily_ndvi(obs)))
            pub["group"] = group
            problems = check_public(pub)
            if problems:
                raise ValueError(f"{fname} is not safe to publish: {problems[:5]}")
            pubs.append(pub)
            out = os.path.join(out_dir, fname)
            with open(out, "w") as fh:
                json.dump(pub, fh, separators=(",", ":"))
            written.append(out)
            f = pub["field"]
            index.append({"id": f["id"], "name": f["name"], "file": fname, "group": group,
                          "rotation_design": f.get("rotation_design"),
                          "current": (pub.get("rotation_options") or {}).get("current")})
    ev_src = os.path.join(profile_dir, "evidence.json")
    if os.path.exists(ev_src):
        with open(ev_src) as fh:
            ev = json.load(fh)
        problems = check_public(ev)
        if problems:
            raise ValueError(f"evidence.json is not safe to publish: {problems[:5]}")
        out = os.path.join(out_dir, "evidence.json")
        with open(out, "w") as fh:
            json.dump(ev, fh, indent=1)
        written.append(out)
    figures = []
    for name, title, caption in FIGURES:
        src = os.path.join(demo_dir, name) if demo_dir else None
        if src and os.path.exists(src):
            dst = os.path.join(out_dir, "fig_" + name.replace("_elora", ""))
            shutil.copyfile(src, dst)
            written.append(dst)
            figures.append({"file": os.path.basename(dst), "title": title, "caption": caption})
    out = os.path.join(out_dir, "index.json")
    with open(out, "w") as fh:
        json.dump({"fields": index, "figures": figures, "highlights": highlights(pubs)}, fh, indent=1)
    written.append(out)
    return written

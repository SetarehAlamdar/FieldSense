"""Export: make the PUBLIC copy of the data that the demo website reads.

The website never reads the private working data. It reads small JSON files published
next to it (docs/data/). This module builds those files and is the privacy gate:

- coordinates are rounded to 2 decimals (about 1 km): enough to say "Elora", not enough
  to locate a plot;
- plot areas and the survey-map source are dropped;
- the barcode is added as numbers (years x 365 days, greenness x 100) so the page can draw it;
- `check_public` refuses anything that still looks private.
"""
import copy
import json
import os
import shutil

import numpy as np
import pandas as pd

from .phenology import barcode_matrix, daily_ndvi

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
    return p


def barcode_payload(obs, since=None):
    """Barcode as compact numbers: greenness x 100 as integers, null where unseen."""
    m = barcode_matrix(daily_ndvi(obs))
    if since:
        m = m[m.index >= since]
    vals = np.round(m.values.astype(float) * 100)
    rows = [[None if np.isnan(v) else int(v) for v in row] for row in vals]
    return {"years": [int(y) for y in m.index], "days": 365, "scale": 100, "values": rows}


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


def export_demo(profile_dir, hls_csv, out_dir, plot_column="plot", demo_dir=None):
    """Write data/index.json, data/evidence.json and data/<field>.json for the website.

    If `demo_dir` is given, the analysis figures listed in FIGURES are copied too
    (as fig_<name>.png) and listed in index.json for the page's gallery.
    Returns the list of files written. Raises ValueError if anything fails `check_public`.
    """
    os.makedirs(out_dir, exist_ok=True)
    hls = pd.read_csv(hls_csv, parse_dates=["date"])
    hls = hls[hls["ndvi"].notna()]
    written, index = [], []
    for fname in sorted(f for f in os.listdir(profile_dir) if f.startswith("plot_") and f.endswith(".json")):
        with open(os.path.join(profile_dir, fname)) as fh:
            prof = json.load(fh)
        plot_no = int(fname.split("_")[1].split(".")[0])
        pub = public_profile(prof)
        pub["barcode"] = barcode_payload(hls[hls[plot_column] == plot_no][["date", "ndvi"]])
        problems = check_public(pub)
        if problems:
            raise ValueError(f"{fname} is not safe to publish: {problems[:5]}")
        out = os.path.join(out_dir, fname)
        with open(out, "w") as fh:
            json.dump(pub, fh, separators=(",", ":"))
        written.append(out)
        f = pub["field"]
        index.append({"id": f["id"], "name": f["name"], "file": fname,
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
        json.dump({"fields": index, "figures": figures}, fh, indent=1)
    written.append(out)
    return written

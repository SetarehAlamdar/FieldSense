"""Field profile: everything FieldSense knows about one field, in one JSON file.

This is the hand-off point between the data work (Lessons 1-5) and the product
(rotation engine, API, website). The website never talks to NASA; it reads profiles.

Rule: every number is stored with `evidence.value()`, i.e. a middle value, a range
(low/high), a unit, what the range means, and the id of the evidence behind it.

Schema version 0.1 (top-level keys):
  schema, field, climate, soil, soil_moisture, history, cover, barcode, gaps
"""
import json

import numpy as np
import pandas as pd

from .evidence import value
from .sources.soilgrids import carbon_stock_t_ha, usda_texture_class

SCHEMA_VERSION = "0.1"


def _pct(series, q):
    return float(np.nanpercentile(series, q)) if len(series) else None


def climate_summary(weather, precip_col="PRECIP_CORR", years=None, rain_evidence=None, temp_evidence=None):
    """Year-to-year climate at the field: median (mid) and 10th-90th percentile (low/high).

    The range here is NATURAL VARIABILITY between years, not measurement error.
    `weather`: daily table indexed by date (Lesson 2's weather_elora_corrected.csv).
    Only complete years count (>= 360 days).
    """
    w = weather.copy()
    if years:
        w = w[(w.index.year >= years[0]) & (w.index.year <= years[1])]
    full = w.groupby(w.index.year).size()
    w = w[w.index.year.isin(full[full >= 360].index)]
    yr = w.index.year
    season = w[(w.index.month >= 5) & (w.index.month <= 9)]
    annual_rain = w[precip_col].groupby(yr).sum()
    season_rain = season[precip_col].groupby(season.index.year).sum()
    gdd = (season["T2M"] - 10).clip(lower=0).groupby(season.index.year).sum()   # corn heat units, base 10 degC
    mean_t = w["T2M"].groupby(yr).mean()

    # Last spring frost and first fall frost (min temperature <= 0 degC), as day of year
    frost = w[w["T2M_MIN"] <= 0]
    last_spring = frost[frost.index.month <= 6].groupby(frost[frost.index.month <= 6].index.year).apply(lambda d: d.index.dayofyear.max())
    first_fall = frost[frost.index.month >= 7].groupby(frost[frost.index.month >= 7].index.year).apply(lambda d: d.index.dayofyear.min())
    frost_free = (first_fall - last_spring).dropna()

    pr = "10th-90th percentile across years"
    def v(s, unit, ev):
        return value(s.median(), _pct(s, 10), _pct(s, 90), unit, ev, pr)
    return {
        "years": [int(yr.min()), int(yr.max())],
        "annual_precip": v(annual_rain, "mm", rain_evidence),
        "season_precip_may_sep": v(season_rain, "mm", rain_evidence),
        "growing_degree_days_may_sep": v(gdd, "degC-days (base 10)", temp_evidence),
        "mean_temperature": v(mean_t, "degC", temp_evidence),
        "last_spring_frost_doy": v(last_spring, "day of year", temp_evidence),
        "first_fall_frost_doy": v(first_fall, "day of year", temp_evidence),
        "frost_free_days": v(frost_free, "days", temp_evidence),
    }


def soil_summary(topsoil, evidence=None):
    """Topsoil (0-30 cm) from `soilgrids.topsoil_summary`, low/mid/high = SoilGrids' 90% interval."""
    units = {"clay": "%", "sand": "%", "silt": "%", "soc": "g/kg", "phh2o": "pH", "bdod": "kg/dm3"}
    pr = "SoilGrids 5%-95% prediction interval"
    out = {p: value(r["mid"], r["low"], r["high"], units.get(p, ""), evidence, pr) for p, r in topsoil.items()}
    if all(k in topsoil for k in ("sand", "silt", "clay")):
        m = {k: topsoil[k]["mid"] for k in ("sand", "silt", "clay")}
        out["texture_class"] = {"class": usda_texture_class(m["sand"], m["silt"], m["clay"]),
                                "evidence": evidence, "note": "from the mid values; the range may span classes"}
    if "soc" in topsoil and "bdod" in topsoil:
        s, b = topsoil["soc"], topsoil["bdod"]
        out["carbon_stock_0_30cm"] = value(carbon_stock_t_ha(s["mid"], b["mid"]),
                                           carbon_stock_t_ha(s["low"], b["mid"]),
                                           carbon_stock_t_ha(s["high"], b["mid"]),
                                           "t C/ha", evidence, "from the SOC range, bulk density at mid")
    return out


def soil_moisture_summary(sm_daily, evidence=None):
    """Typical root-zone wetness by month (SMAP L4), median and 10th-90th percentile across years."""
    if sm_daily is None or "rootzone" not in sm_daily:
        return None
    s = sm_daily["rootzone"].dropna()
    monthly = s.groupby([s.index.year, s.index.month]).mean()
    by_month = monthly.groupby(level=1)
    pr = "10th-90th percentile across years"
    return {
        "years": [int(s.index.year.min()), int(s.index.year.max())],
        "rootzone_by_month": {int(m): value(g.median(), _pct(g, 10), _pct(g, 90), "m3/m3", evidence, pr)
                              for m, g in by_month},
    }


def build_field_profile(field, history, cover, climate=None, soil=None, soil_moisture=None,
                        barcode_file=None, history_evidence=None, gaps=None):
    """Assemble the profile dict.

    field:   {"id", "name", "lat", "lon", "area_ha", ...}
    history: DataFrame from `phenology.field_history` (one row per year)
    cover:   DataFrame from `phenology.cover_summary` (indexed by year)
    gaps:    list of plain-language information gaps (what we do NOT know)
    """
    hist_rows = []
    for _, r in history.iterrows():
        hist_rows.append({
            "year": int(r["year"]),
            "satellite_says": r["satellite_says"],
            "n_clear_looks": int(r["n_obs"]),
            "peak_ndvi": None if pd.isna(r["peak_ndvi"]) else round(float(r["peak_ndvi"]), 3),
            "peak_doy": None if pd.isna(r["peak_doy"]) else int(r["peak_doy"]),
            "evidence": history_evidence,
        })
    as_num = lambda v: None if pd.isna(v) else (float(v) if isinstance(v, float) else int(v))
    cover_rows = [{"year": int(y), **{k: as_num(v) for k, v in row.items()}} for y, row in cover.iterrows()]
    recent = cover.tail(5)
    return {
        "schema": SCHEMA_VERSION,
        "field": field,
        "climate": climate,
        "soil": soil,
        "soil_moisture": soil_moisture,
        "history": hist_rows,
        "cover": {
            "per_year": cover_rows,
            "recent_mean_green_days_off_season": round(float(recent["green_days_off_season"].mean()), 1) if len(recent) else None,
            "recent_mean_bare_days": round(float(recent["bare_days"].mean()), 1) if len(recent) else None,
            "recent_green_share_off_season": round(float(recent["green_share_off_season"].mean()), 3) if len(recent) else None,
            "evidence": history_evidence,
        },
        "barcode": barcode_file,
        "gaps": gaps or [],
    }


def check_profile(profile):
    """Basic rules every profile must follow. Returns a list of problems (empty = OK)."""
    problems = []
    for key in ("schema", "field", "history", "cover", "gaps"):
        if key not in profile:
            problems.append(f"missing key: {key}")

    def walk(node, path):
        if isinstance(node, dict):
            if {"mid", "low", "high"} <= node.keys():
                lo, mid, hi = node["low"], node["mid"], node["high"]
                if None not in (lo, mid, hi) and not lo <= mid <= hi:
                    problems.append(f"{path}: low <= mid <= high violated ({lo}, {mid}, {hi})")
                if node.get("evidence") is None:
                    problems.append(f"{path}: number has no evidence id")
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(profile, "profile")
    return problems


def save_profile(profile, path):
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)


def load_profile(path):
    with open(path) as f:
        return json.load(f)

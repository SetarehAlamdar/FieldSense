"""Field profile: everything FieldSense knows about one field, in one JSON file.

This is the hand-off point between the data pipeline and the product
(rotation engine, API, website). The website never talks to NASA; it reads profiles.

Rule: every number is stored with `evidence.value()`, i.e. a middle value, a range
(low/high), a unit, what the range means, and the id of the evidence behind it.

Schema version 0.3 (top-level keys):
  schema, field, climate, climate_odds, rotation_options, soil, soil_moisture, history, cover, barcode, gaps
  0.1 -> 0.2 added `climate_odds` and more climate indicators; nothing was removed or renamed,
  so a reader written for 0.1 still works (a backward-compatible change).
  0.2 -> 0.3 added `rotation_options`: the rotation comparison, ranking robustness
  and five-part explanations. Also backward compatible.
"""
import json

import numpy as np
import pandas as pd

from .climate import indicators_by_year, risk_counts
from .evidence import value
from .sources.soilgrids import carbon_stock_t_ha, usda_texture_class

SCHEMA_VERSION = "0.3"   # 0.3: adds optional rotation_options (backward compatible)


def _pct(series, q):
    return float(np.nanpercentile(series, q)) if len(series) else None


def climate_summary(weather, precip_col="PRECIP_CORR", years=None, rain_evidence=None, temp_evidence=None):
    """Year-to-year climate at the field: median (mid) and 10th-90th percentile (low/high).

    The range here is NATURAL VARIABILITY between years, not measurement error.
    `weather`: daily table indexed by date. Only complete years count (>= 360 days).
    The indicators themselves are computed in `climate.year_indicators` (one place only).
    """
    w = weather
    if years:
        w = w[(w.index.year >= years[0]) & (w.index.year <= years[1])]
    ind = indicators_by_year(w, rain=precip_col)
    units = {
        "annual_precip": ("mm", rain_evidence), "season_precip_may_sep": ("mm", rain_evidence),
        "growing_degree_days_may_sep": ("degC-days (base 10)", temp_evidence), "mean_temperature": ("degC", temp_evidence),
        "last_spring_frost_doy": ("day of year", temp_evidence), "first_fall_frost_doy": ("day of year", temp_evidence),
        "frost_free_days": ("days", temp_evidence), "heat_days_pollination": ("days", temp_evidence),
        "heavy_rain_days_spring": ("days", rain_evidence), "heavy_rain_days_year": ("days", rain_evidence),
        "longest_dry_spell_summer": ("days", rain_evidence), "fall_gdd5_sep_nov": ("degC-days (base 5)", temp_evidence),
    }
    pr = "10th-90th percentile across years"
    out = {"years": [int(ind.index.min()), int(ind.index.max())]}
    for col, (unit, ev) in units.items():
        s = ind[col].dropna().astype(float)
        out[col] = value(s.median(), _pct(s, 10), _pct(s, 90), unit, ev, pr)
    return out


def climate_odds(futures, history, risks=None, evidence=None, target_year=2026):
    """Risks for next season as "X in 100 futures", next to how often they happened in real years.

    Showing both keeps us honest: 100 futures are built from ~30 real years,
    so "20 in 100" is really "about 6 of 30 past years, adjusted to today's warmth".
    """
    f, h = risk_counts(futures, risks), risk_counts(history, risks)
    return {
        "target_year": target_year,
        "n_futures": int(len(futures)),
        "risks": {k: {"text": f[k]["text"], "futures": f"{f[k]['count']} in {f[k]['of']}",
                      "past_years": f"{h[k]['count']} of {h[k]['of']}", "share": round(f[k]["count"] / max(f[k]["of"], 1), 3),
                      "evidence": evidence or []} for k in f},
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
                        barcode_file=None, history_evidence=None, gaps=None, climate_odds=None):
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
        "climate_odds": climate_odds,
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

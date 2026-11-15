"""FieldSense at any location in Canada: nearest station, corrected NASA POWER, next-season odds.

For a point (lat, lon):
1. find the nearest Environment and Climate Change Canada (ECCC) station with a long daily
   record (`nearest_stations`, from ECCC's open station list),
2. download 30 years of NASA POWER at the point and the station's daily record,
3. correct POWER with the station, the same way as at Elora (Lesson 6): rain multiplied by a
   factor per calendar month, temperature shifted by an offset per calendar month, both checked
   on held-out years,
4. build 1,000 possible seasons for the next season (2027) by year-block bootstrap, brought to
   today's warmth only if the warming trend's whole 90% interval is above zero (rule set before).

`climate_from_frames` does steps 3-4 on data already downloaded, so it can be tested offline.
If no usable station is found, POWER is used uncorrected and labelled "modelled".
"""
import math

import numpy as np
import pandas as pd

from .climate import (apply_monthly_offsets, held_out_offset_check, indicators_by_year, make_futures,
                      monthly_offsets, risk_counts, warming_trend)
from .correction import factors_from, held_out_error
from .rotation import NEXT_SEASON

STATIONS_URL = "https://api.weather.gc.ca/collections/climate-stations/items"
FIRST_YEAR, LAST_YEAR = 1996, 2025


def _km(lon1, lat1, lon2, lat2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _year(v):
    try:
        return int(str(v)[:4])
    except (TypeError, ValueError):
        return None


def pick_stations(features, lon, lat, min_years=15, first=FIRST_YEAR, last=LAST_YEAR):
    """Stations (GeoJSON features from ECCC's station list) with at least `min_years` of daily
    data inside first..last, nearest first: [{"id", "name", "km", "first", "last", "years"}]."""
    out = []
    for f in features:
        p = {k.upper(): v for k, v in (f.get("properties") or {}).items()}
        geom = f.get("geometry") or {}
        if not geom.get("coordinates") or p.get("STN_ID") is None:
            continue
        slon, slat = geom["coordinates"][:2]
        a, b = _year(p.get("DLY_FIRST_DATE")), _year(p.get("DLY_LAST_DATE"))
        if a is None or b is None:
            continue
        years = min(b, last) - max(a, first) + 1
        if years >= min_years:
            out.append({"id": int(p["STN_ID"]), "name": str(p.get("STATION_NAME", "")).title(),
                        "km": round(_km(lon, lat, slon, slat), 1), "first": a, "last": b, "years": years})
    return sorted(out, key=lambda s: s["km"])


def nearest_stations(lon, lat, radius_deg=1.0, min_years=15):
    """ECCC stations near a point with a long daily record, nearest first (needs internet)."""
    import requests
    bbox = f"{lon - radius_deg * 1.5},{lat - radius_deg},{lon + radius_deg * 1.5},{lat + radius_deg}"
    r = requests.get(STATIONS_URL, params={"bbox": bbox, "f": "json", "limit": 1000}, timeout=60)
    r.raise_for_status()
    return pick_stations(r.json().get("features", []), lon, lat, min_years=min_years)


def _monthly_totals(s, min_cover=0.9):
    g = s.groupby([s.index.year, s.index.month])
    ok = (g.count() / g.size()) >= min_cover
    return g.sum()[ok]


def climate_from_frames(power, station=None, station_info=None, target_year=NEXT_SEASON, n_futures=1000, seed=2026):
    """Corrected weather, indicators and next-season odds from data already downloaded.

    power: daily DataFrame with T2M, T2M_MIN, T2M_MAX, PRECTOTCORR (NASA POWER).
    station: daily DataFrame with tmax, tmin, tmean, precip (ECCC), or None.
    """
    w = power[["T2M", "T2M_MIN", "T2M_MAX", "PRECTOTCORR"]].astype(float).interpolate(limit=3, limit_area="inside")
    w = w[(w.index.year >= FIRST_YEAR) & (w.index.year <= LAST_YEAR)]
    out = {"station": station_info, "correction": {}}
    rain = w["PRECTOTCORR"].copy()
    daily = pd.DataFrame(index=w.index)
    corrected = False
    if station is not None and len(station):
        st = station[(station.index.year >= FIRST_YEAR) & (station.index.year <= LAST_YEAR)]
        sm = _monthly_totals(st["precip"].dropna().reindex(st.index))
        pm = _monthly_totals(rain).reindex(sm.index).dropna()
        sm = sm.reindex(pm.index)
        if len(sm) >= 120:                                   # 10+ years of complete months
            f = factors_from(sm, pm).clip(0.5, 2.0)
            rain = rain * rain.index.month.map(f).values
            years = sorted(set(sm.index.get_level_values(0)))
            split = years[len(years) // 2]
            raw, corr = held_out_error(sm, pm, split)
            out["correction"]["rain"] = {"held_out_error_raw_pct": round(float(raw), 1),
                                         "held_out_error_corrected_pct": round(float(corr), 1),
                                         "factors": {int(k): round(float(v), 3) for k, v in f.items()}}
            corrected = True
        for col, scol in (("T2M", "tmean"), ("T2M_MIN", "tmin"), ("T2M_MAX", "tmax")):
            s = st[scol].dropna()
            if len(s) >= 3650:
                off = monthly_offsets(s, w[col])
                daily[col] = apply_monthly_offsets(w[col], off)
                if col == "T2M_MIN":
                    years = sorted(set(s.index.year))
                    chk = held_out_offset_check(s, w[col], years[len(years) // 2])
                    out["correction"]["temperature"] = {
                        "bias_raw_c": round(chk["bias_raw"], 2), "bias_corrected_c": round(chk["bias_corrected"], 2),
                        "mae_raw_c": round(chk["mae_raw"], 2), "mae_corrected_c": round(chk["mae_corrected"], 2)}
            else:
                daily[col] = w[col]
    else:
        for col in ("T2M", "T2M_MIN", "T2M_MAX"):
            daily[col] = w[col]
    daily["PRECIP_CORR"] = rain
    hist = indicators_by_year(daily)
    trend = warming_trend(hist["mean_temperature"])
    shift = trend["slope_per_year"] if trend["low"] > 0 else 0.0
    fut = make_futures(daily, n=n_futures, target_year=target_year, temp_trend=shift, seed=seed)
    f, h = risk_counts(fut), risk_counts(hist)
    risks = {k: {"text": f[k]["text"], "share": round(f[k]["count"] / max(f[k]["of"], 1), 3),
                 "futures": f"{f[k]['count']} in {f[k]['of']}", "past_years": f"{h[k]['count']} of {h[k]['of']}"}
             for k in f if not k.startswith("short_fall_for_cover")}
    med = lambda c: round(float(hist[c].median()), 1)
    out.update({
        "corrected": corrected,
        "evidence": "validated" if corrected else "modelled",
        "years": [int(hist.index.min()), int(hist.index.max())],
        "summary": {"annual_precip_mm": med("annual_precip"), "gdd10_may_sep": med("growing_degree_days_may_sep"),
                    "frost_free_days": med("frost_free_days"), "last_spring_frost_doy": med("last_spring_frost_doy"),
                    "first_fall_frost_doy": med("first_fall_frost_doy")},
        "trend": {"c_per_decade": round(10 * trend["slope_per_year"], 2), "low": round(10 * trend["low"], 2),
                  "high": round(10 * trend["high"], 2), "shifted": shift > 0},
        "odds": {"target_year": target_year, "n_futures": n_futures, "risks": risks},
    })
    return out


def climate_for_point(lat, lon, cache_dir="data_cache", station_id=None, min_years=15):
    """Steps 1-4 for one point (needs internet). Returns the dict of `climate_from_frames`."""
    from .sources.power import get_power_daily
    from .sources.stations import get_eccc_years
    lat, lon = round(lat, 2), round(lon, 2)
    power = get_power_daily(lat, lon, f"{FIRST_YEAR}0101", f"{LAST_YEAR}1231",
                            parameters=["T2M", "T2M_MIN", "T2M_MAX", "PRECTOTCORR"], cache_dir=cache_dir)
    info, station = None, None
    try:
        cands = nearest_stations(lon, lat, min_years=min_years)
        if station_id:
            cands = [c for c in cands if c["id"] == int(station_id)] or [{"id": int(station_id), "name": "chosen station", "km": None}]
        for c in cands[:3]:                                   # nearest first; skip one that fails
            try:
                st = get_eccc_years(c["id"], max(FIRST_YEAR, c.get("first") or FIRST_YEAR),
                                    min(LAST_YEAR, c.get("last") or LAST_YEAR), cache_dir=cache_dir)
                if st[["tmin", "precip"]].notna().sum().min() >= 3650:
                    info, station = c, st
                    break
            except Exception as e:
                print(f"  station {c['id']} {c.get('name')}: {type(e).__name__}, trying the next one")
    except Exception as e:
        print(f"  station search failed ({type(e).__name__}): using NASA POWER uncorrected")
    if info:
        print(f"  station: {info['name']} (ECCC {info['id']}), {info['km']} km away")
    return climate_from_frames(power, station, info)

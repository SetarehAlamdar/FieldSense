"""Checks for fieldsense.anywhere: station choice and the climate pipeline, on fake data (no internet)."""
import numpy as np
import pandas as pd

from fieldsense import anywhere as aw
from fieldsense import canada as ca


def fake_power(seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1996-01-01", "2025-12-31", freq="D")
    doy = idx.dayofyear.values
    t = 6 + 14 * np.sin(2 * np.pi * (doy - 110) / 365) + rng.normal(0, 3, len(idx)) + 0.03 * (idx.year - 1996)
    rain = np.where(rng.random(len(idx)) < 0.3, rng.gamma(1.2, 6, len(idx)), 0.0)
    return pd.DataFrame({"T2M": t, "T2M_MIN": t - 5, "T2M_MAX": t + 5, "PRECTOTCORR": rain}, index=idx)


def test_pick_stations_keeps_long_records_nearest_first():
    feats = [
        {"geometry": {"coordinates": [-106.0, 52.0]}, "properties": {"STN_ID": 1, "STATION_NAME": "NEAR SHORT",
         "DLY_FIRST_DATE": "2018-01-01", "DLY_LAST_DATE": "2025-12-31"}},
        {"geometry": {"coordinates": [-106.3, 52.1]}, "properties": {"STN_ID": 2, "STATION_NAME": "MID LONG",
         "DLY_FIRST_DATE": "1980-05-01 00:00:00", "DLY_LAST_DATE": "2025-11-01"}},
        {"geometry": {"coordinates": [-107.5, 52.6]}, "properties": {"stn_id": 3, "station_name": "FAR LONG",
         "dly_first_date": "1950-01-01", "dly_last_date": "2024-12-31"}},
    ]
    st = aw.pick_stations(feats, -106.1, 52.0)
    assert [s["id"] for s in st] == [2, 3]                    # 8-year record dropped
    assert st[0]["name"] == "Mid Long" and st[0]["km"] < st[1]["km"]


def test_climate_corrects_power_with_the_station_and_gives_2027_odds():
    p = fake_power()
    station = pd.DataFrame({"tmean": p["T2M"] - 1.0, "tmin": p["T2M_MIN"] - 1.0, "tmax": p["T2M_MAX"] - 1.0,
                            "precip": p["PRECTOTCORR"] * 1.25}, index=p.index)   # POWER 1 C warm, 20% dry
    out = aw.climate_from_frames(p, station, {"id": 9, "name": "Test", "km": 12.0}, n_futures=200)
    assert out["corrected"] and out["evidence"] == "validated"
    assert abs(out["correction"]["temperature"]["bias_raw_c"] - 1.0) < 0.05
    assert abs(out["correction"]["temperature"]["bias_corrected_c"]) < 0.05
    assert abs(out["correction"]["rain"]["held_out_error_corrected_pct"]) < 3
    assert out["odds"]["target_year"] == 2027 and out["odds"]["n_futures"] == 200
    assert "heavy_rain_on_bare_soil" in out["odds"]["risks"] and out["trend"]["shifted"]


def test_climate_without_station_is_labelled_modelled():
    out = aw.climate_from_frames(fake_power(1), None, None, n_futures=50)
    assert not out["corrected"] and out["evidence"] == "modelled" and out["station"] is None


def test_custom_place_goes_into_canada_json(tmp_path):
    import json
    years = [2024, 2025]
    row = np.full(365, 0.2); row[160:230] = 0.8
    m = pd.DataFrame(np.vstack([row, row]), index=years, columns=range(1, 366))
    recs = [ca.field_record(i, f"Field {i}", g, {2024: 153, 2025: 146}, m) for i, g in ((1, "simple"), (2, "simple"), (3, "diverse"))]
    clim = aw.climate_from_frames(fake_power(2), None, None, n_futures=50)
    place = {"x": {"name": "My farm", "place": "Near Rosetown, SK", "lon": -107.98, "lat": 51.55, "system": "your choice"}}
    ca.export_canada({"x": recs}, tmp_path / "c.json", places=place, climate={"x": clim})
    d = json.loads((tmp_path / "c.json").read_text())
    r = d["regions"][0]
    assert r["custom"] and r["name"] == "My farm" and r["climate"]["odds"]["target_year"] == 2027

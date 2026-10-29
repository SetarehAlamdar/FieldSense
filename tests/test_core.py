"""Automated checks. Run with:  pytest

Each test builds a small, fake input where we KNOW the right answer, then checks the code
gets it. Remember the Lesson 4 lesson: these tests catch code bugs, not wrong assumptions.
Assumptions (like the wheat threshold) are checked against real ground truth instead.
"""
import numpy as np
import pandas as pd
import pytest

import fieldsense as fs
from fieldsense.sources.soilgrids import carbon_stock_t_ha, topsoil_summary, usda_texture_class


# ---------- correction ----------
def _monthly(values_by_year):
    idx = pd.MultiIndex.from_tuples([(y, m) for y in values_by_year for m in range(1, 13)])
    return pd.Series([v for y in values_by_year for v in values_by_year[y]], index=idx)


def test_model_that_is_always_20pct_low_is_fully_corrected():
    station = _monthly({y: [100.0] * 12 for y in range(2000, 2010)})
    model = station * 0.8
    raw, corrected = fs.held_out_error(station, model, split_year=2004)
    assert raw == pytest.approx(-20)
    assert corrected == pytest.approx(0, abs=1e-9)


def test_apply_monthly_scaling_uses_each_days_month():
    days = pd.date_range("2020-01-30", "2020-02-02")
    out = fs.apply_monthly_scaling(pd.Series(1.0, index=days), pd.Series({1: 2.0, 2: 3.0}))
    assert out.tolist() == [2.0, 2.0, 3.0, 3.0]


# ---------- soil ----------
@pytest.mark.parametrize("sand,silt,clay,expected", [
    (90, 5, 5, "sand"), (40, 40, 20, "loam"), (20, 20, 60, "clay"), (10, 70, 20, "silt loam"),
])
def test_texture_classes(sand, silt, clay, expected):
    assert usda_texture_class(sand, silt, clay) == expected


def test_carbon_stock_formula():
    assert carbon_stock_t_ha(20, 1.3, 30) == pytest.approx(78)


def test_topsoil_summary_weights_by_thickness():
    rows = [("clay", d, s, v) for d, v in [("0-5cm", 10), ("5-15cm", 20), ("15-30cm", 30)]
            for s in ("Q0.05", "mean", "Q0.95")]
    t = pd.DataFrame(rows, columns=["property", "depth", "statistic", "value"])
    assert topsoil_summary(t)["clay"]["mid"] == pytest.approx((10 * 5 + 20 * 10 + 30 * 15) / 30)


# ---------- phenology ----------
def _season(year, peak_doy, peak=0.85, base=0.2, width=25, cover_doys=()):
    """Fake clear looks every 5 days: a bell-shaped crop curve, plus optional green cover days."""
    doys = np.arange(60, 335, 5)
    ndvi = base + (peak - base) * np.exp(-0.5 * ((doys - peak_doy) / width) ** 2)
    for lo, hi in cover_doys:
        ndvi = np.where((doys >= lo) & (doys <= hi), np.maximum(ndvi, 0.6), ndvi)
    dates = pd.Timestamp(year, 1, 1) + pd.to_timedelta(doys - 1, unit="D")
    return pd.DataFrame({"date": dates, "ndvi": ndvi})


def test_wheat_peaks_early_and_corn_late():
    obs = pd.concat([_season(2020, 170), _season(2021, 215)])
    hist = fs.field_history(obs)
    assert hist.loc[hist.year == 2020, "satellite_says"].item().startswith("winter wheat")
    assert hist.loc[hist.year == 2021, "satellite_says"].item().startswith("corn or soybean")


def test_fall_cover_crop_is_flagged():
    hist = fs.field_history(_season(2020, 215, cover_doys=[(280, 330)]))
    assert "green after harvest" in hist["satellite_says"].item()


def test_daily_ndvi_does_not_invent_values_across_long_gaps():
    obs = pd.DataFrame({"date": pd.to_datetime(["2020-05-01", "2020-05-11", "2020-08-01", "2020-08-06"]),
                        "ndvi": [0.3, 0.4, 0.8, 0.8]})
    s = fs.daily_ndvi(obs, max_gap_days=30)
    assert s["2020-05-06"] == pytest.approx(0.35, abs=0.06)   # short gap: interpolated
    assert np.isnan(s["2020-06-15"])                          # 82-day gap: left missing


def test_barcode_has_365_columns_even_in_leap_years():
    s = fs.daily_ndvi(pd.concat([_season(2020, 200), _season(2021, 200)]))
    m = fs.barcode_matrix(s)
    assert list(m.columns) == list(range(1, 366)) and list(m.index) == [2020, 2021]


def test_cover_summary_counts_off_season_green():
    with_cover = fs.barcode_matrix(fs.daily_ndvi(_season(2020, 215, cover_doys=[(280, 330)])))
    without = fs.barcode_matrix(fs.daily_ndvi(_season(2020, 215)))
    assert fs.cover_summary(with_cover)["green_days_off_season"].item() > \
           fs.cover_summary(without)["green_days_off_season"].item() + 30


# ---------- evidence ----------
def test_evidence_round_trip(tmp_path):
    reg = fs.EvidenceRegistry()
    reg.add(fs.Evidence("rain", "validated", "Rainfall is right within 5%", "NASA POWER",
                        test="held-out years", result="-26% -> -5%"))
    reg.add(fs.Evidence("soil", "modelled", "Topsoil is a loam", "SoilGrids"))
    reg.to_json(tmp_path / "e.json")
    back = fs.EvidenceRegistry.from_json(tmp_path / "e.json")
    assert back.get("rain").result == "-26% -> -5%"
    assert back.weakest(["rain", "soil"]) == "modelled"


def test_validated_evidence_must_report_its_test():
    with pytest.raises(ValueError):
        fs.Evidence("x", "validated", "claim", "source")


def test_value_rejects_inverted_range():
    with pytest.raises(ValueError):
        fs.value(5, low=6, high=7)


# ---------- profile ----------
def _fake_weather():
    days = pd.date_range("2001-01-01", "2010-12-31")
    rng = np.random.default_rng(0)
    t = 7 + 14 * np.sin(2 * np.pi * (days.dayofyear - 110) / 365)
    return pd.DataFrame({"T2M": t, "T2M_MIN": t - 5, "T2M_MAX": t + 5,
                         "PRECIP_CORR": rng.gamma(0.6, 4, len(days))}, index=days)


def test_profile_is_complete_and_ranges_are_ordered(tmp_path):
    obs = pd.concat([_season(2020, 170), _season(2021, 215, cover_doys=[(280, 330)])])
    hist = fs.field_history(obs)
    cover = fs.cover_summary(fs.barcode_matrix(fs.daily_ndvi(obs)))
    climate = fs.climate_summary(_fake_weather(), rain_evidence="rain", temp_evidence="temp")
    soil = fs.soil_summary({"clay": {"low": 15, "mid": 22, "high": 30},
                            "sand": {"low": 25, "mid": 35, "high": 45},
                            "silt": {"low": 35, "mid": 43, "high": 50},
                            "soc": {"low": 8, "mid": 15, "high": 40},
                            "bdod": {"low": 1.2, "mid": 1.35, "high": 1.5}}, evidence="soil")
    p = fs.build_field_profile({"id": "test"}, hist, cover, climate=climate, soil=soil,
                               history_evidence="hls", gaps=["Corn vs soybean not separated"])
    assert fs.check_profile(p) == []
    assert soil["texture_class"]["class"] == "loam"
    fs.save_profile(p, tmp_path / "p.json")
    assert fs.load_profile(tmp_path / "p.json")["history"][0]["satellite_says"].startswith("winter wheat")


def test_check_profile_catches_numbers_without_evidence():
    p = {"schema": "0.1", "field": {}, "history": [], "cover": {}, "gaps": [],
         "climate": {"rain": {"low": 1, "mid": 2, "high": 3, "evidence": None}}}
    assert any("no evidence" in x for x in fs.check_profile(p))


def test_same_day_landsat_and_sentinel_looks_are_averaged():
    obs = pd.DataFrame({"date": ["2020-07-01", "2020-07-01", "2020-07-06"], "ndvi": [0.6, 0.8, 0.7]})
    from fieldsense.phenology import prepare
    d = prepare(obs)
    assert len(d) == 2 and d["ndvi"].iloc[0] == pytest.approx(0.7)

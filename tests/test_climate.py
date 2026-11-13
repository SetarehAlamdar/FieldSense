"""Checks for fieldsense.climate. Each test uses weather where we know the answer."""
import numpy as np
import pandas as pd
import pytest

import fieldsense as fs
from fieldsense.climate import year_indicators


def _year(y=2020, tmin_base=-5.0, rain=0.0):
    """A simple year: smooth seasonal temperature, constant rain."""
    d = pd.date_range(f"{y}-01-01", f"{y}-12-31")
    t = 7 + 14 * np.sin(2 * np.pi * (d.dayofyear - 110) / 365)
    return pd.DataFrame({"T2M": t, "T2M_MIN": t + tmin_base, "T2M_MAX": t + 5, "PRECIP_CORR": rain}, index=d)


def _many_years(first=1996, last=2025, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for y in range(first, last + 1):
        f = _year(y)
        f["PRECIP_CORR"] = rng.gamma(0.5, 5, len(f))
        frames.append(f)
    return pd.concat(frames)


def test_offsets_remove_a_constant_warm_bias():
    s = _year()["T2M_MIN"]
    model = s + 2.0                                   # model nights 2 degC too warm
    off = fs.monthly_offsets(s, model)
    assert np.allclose(off.values, -2.0)
    assert np.allclose(fs.apply_monthly_offsets(model, off), s)


def test_held_out_check_reports_bias_before_and_after():
    s = pd.concat([_year(y)["T2M_MIN"] for y in range(2004, 2010)])
    r = fs.held_out_offset_check(s, s + 1.5, split_year=2006)
    assert r["bias_raw"] == pytest.approx(1.5)
    assert r["bias_corrected"] == pytest.approx(0, abs=1e-9)


def test_frost_dates_move_when_nights_get_colder():
    warm, cold = year_indicators(_year(tmin_base=-5)), year_indicators(_year(tmin_base=-8))
    assert cold["last_spring_frost_doy"] > warm["last_spring_frost_doy"]
    assert cold["frost_free_days"] < warm["frost_free_days"]


def test_dry_spell_and_heavy_rain():
    d = _year(rain=2.0)
    d.loc["2020-07-01":"2020-07-20", "PRECIP_CORR"] = 0.0      # 20 dry days
    d.loc["2020-05-10", "PRECIP_CORR"] = 40.0                  # one storm on bare soil
    ind = year_indicators(d)
    assert ind["longest_dry_spell_summer"] == 20
    assert ind["heavy_rain_days_spring"] == 1


def test_risk_counts():
    t = pd.DataFrame({"heat_days_pollination": [0, 3, 5, 1]})
    r = fs.risk_counts(t, {"heat": ("heat_days_pollination", ">=", 3, "hot")})
    assert r["heat"]["count"] == 2 and r["heat"]["of"] == 4


def test_warming_trend_finds_a_known_slope():
    years = np.arange(1996, 2026)
    rng = np.random.default_rng(1)
    s = pd.Series(7 + 0.03 * (years - 1996) + rng.normal(0, 0.3, len(years)), index=years)
    tr = fs.warming_trend(s, n_boot=500)
    assert tr["low"] < 0.03 < tr["high"]


def test_futures_are_reproducible_and_shift_temperature():
    w = _many_years(2016, 2025)
    a = fs.make_futures(w, n=20, temp_trend=0.05, seed=7)
    b = fs.make_futures(w, n=20, temp_trend=0.05, seed=7)
    pd.testing.assert_frame_equal(a, b)                         # same seed -> same futures
    expected = 0.05 * (2026 - a["source_year"])
    assert np.allclose(a["temp_shift"], expected)               # no temp noise -> pure trend shift
    assert (a["rain_factor"] >= 0).all()


def test_climate_odds_shows_futures_and_past_years():
    w = _many_years(2016, 2025)
    hist = fs.indicators_by_year(w)
    fut = fs.make_futures(w, n=50, seed=3)
    odds = fs.climate_odds(fut, hist, evidence=["power_temperature"])
    r = odds["risks"]["summer_dry_spell"]
    assert r["futures"].endswith("in 50") and r["past_years"].endswith("of 10")


def test_frost_dates_skip_years_with_too_many_missing_days():
    s = pd.concat([_year(2019)["T2M_MIN"], _year(2020)["T2M_MIN"]])
    s.loc["2020-03-01":"2020-05-31"] = np.nan                  # a spring with no readings
    fd = fs.frost_dates(s)
    assert list(fd.index) == [2019]


def test_uninformative_risks_are_flagged():
    counts = {"never": {"count": 0, "of": 100}, "useful": {"count": 30, "of": 100}, "always": {"count": 100, "of": 100}}
    assert fs.uninformative_risks(counts) == ["never", "always"]

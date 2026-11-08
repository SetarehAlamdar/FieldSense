"""Climate: yearly indicators, temperature correction, and 100 possible next seasons.

Lesson 6. Three ideas:

1. TEMPERATURE CORRECTION is ADDITIVE (rain was multiplicative). If POWER's nights are
   2 degC too warm, they're 2 degC too warm whether it's -10 or +10. Multiplying would
   be meaningless (and breaks at 0 degC). Rain is the opposite: being 25% low scales with
   how much fell, and a dry day must stay dry.

2. INDICATORS turn 365 days of weather into a few numbers per year that matter for a
   rotation decision (frost dates, heat at corn pollination, heavy rain on bare soil...).

3. FUTURES by YEAR-BLOCK BOOTSTRAP: a possible next season = a real past year, whole,
   brought to today's warmth, plus a small random error. Sampling whole years keeps
   everything that happens TOGETHER in real weather: a dry spell is many dry days in a row,
   and hot days come with little rain. Sampling single days would destroy both.
   Limit: with 30 past years, the futures can't be more varied than those 30 years.
"""
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- correction
def monthly_offsets(station, model):
    """Additive correction per calendar month: mean(station - model) on days both have."""
    both = pd.concat([station.rename("s"), model.rename("m")], axis=1).dropna()
    return (both["s"] - both["m"]).groupby(both.index.month).mean()


def apply_monthly_offsets(daily, offsets):
    """Add each day's month offset (offsets indexed 1..12)."""
    return daily + daily.index.month.map(offsets).values


def held_out_offset_check(station, model, split_year):
    """Fit offsets on years <= split_year; on later years return mean errors before/after.

    Returns dict: bias_raw, bias_corrected (mean model - station, degC),
    mae_raw, mae_corrected (mean absolute daily error, degC), and the corrected
    daily residuals on the test years (used later as the size of the remaining error).
    """
    train = station.index.year <= split_year
    off = monthly_offsets(station[train], model[model.index.year <= split_year])
    test_s = station[~train].dropna()
    test_m = model.reindex(test_s.index)
    corr = apply_monthly_offsets(test_m, off)
    resid = corr - test_s
    return {"bias_raw": float((test_m - test_s).mean()), "bias_corrected": float(resid.mean()),
            "mae_raw": float((test_m - test_s).abs().mean()), "mae_corrected": float(resid.abs().mean()),
            "residuals": resid}


# ---------------------------------------------------------------- indicators
def _first_last_frost(tmin, threshold=0.0):
    """Day of year of the last spring frost (Jan-Jun) and the first fall frost (Jul-Dec)."""
    frost = tmin[tmin <= threshold]
    spring, fall = frost[frost.index.month <= 6], frost[frost.index.month >= 7]
    last = spring.index.dayofyear.max() if len(spring) else np.nan
    first = fall.index.dayofyear.min() if len(fall) else np.nan
    return float(last), float(first)


def frost_dates(tmin, threshold=0.0, min_days=330):
    """Per year: last spring frost, first fall frost (day of year) and frost-free days.

    Works on station data with gaps: years with fewer than `min_days` readings are skipped,
    because a missing cold night could move the frost date.
    """
    rows = {}
    for y, s in tmin.dropna().groupby(tmin.dropna().index.year):
        if len(s) >= min_days:
            last, first = _first_last_frost(s, threshold)
            rows[y] = {"last_spring_frost_doy": last, "first_fall_frost_doy": first, "frost_free_days": first - last}
    return pd.DataFrame(rows).T.rename_axis("year")


def _longest_run(mask):
    best = run = 0
    for m in mask:
        run = run + 1 if m else 0
        best = max(best, run)
    return best


def _between(d, m1, d1, m2, d2):
    y = d.index[0].year
    return d[(d.index >= pd.Timestamp(y, m1, d1)) & (d.index <= pd.Timestamp(y, m2, d2))]


def year_indicators(d, rain="PRECIP_CORR", tmin="T2M_MIN", tmax="T2M_MAX", tmean="T2M"):
    """Indicators for ONE calendar year of daily weather (a DataFrame indexed by date)."""
    last, first = _first_last_frost(d[tmin])
    season = _between(d, 5, 1, 9, 30)
    pollination = _between(d, 7, 10, 8, 10)          # corn tasselling/silking at Elora
    spring_bare = _between(d, 4, 15, 6, 15)           # corn/soy fields mostly bare soil
    summer = _between(d, 6, 1, 8, 31)
    fall = _between(d, 9, 1, 11, 30)
    after_soy = _between(d, 9, 25, 11, 30)            # cover crop sown right after soybean harvest
    return {
        "annual_precip": d[rain].sum(),
        "season_precip_may_sep": season[rain].sum(),
        "growing_degree_days_may_sep": (season[tmean] - 10).clip(lower=0).sum(),
        "mean_temperature": d[tmean].mean(),
        "last_spring_frost_doy": last,
        "first_fall_frost_doy": first,
        "frost_free_days": first - last,
        "heat_days_pollination": int((pollination[tmax] >= 32).sum()),
        "heavy_rain_days_spring": int((spring_bare[rain] >= 25).sum()),
        "heavy_rain_days_year": int((d[rain] >= 25).sum()),
        "longest_dry_spell_summer": _longest_run((summer[rain] < 1).values),
        "fall_gdd5_sep_nov": (fall[tmean] - 5).clip(lower=0).sum(),
        "fall_gdd5_after_soybean": (after_soy[tmean] - 5).clip(lower=0).sum(),
    }


def indicators_by_year(daily, min_days=360, **cols):
    """One row per complete year."""
    rows = {}
    for y, d in daily.groupby(daily.index.year):
        if len(d) >= min_days:
            rows[y] = year_indicators(d, **cols)
    return pd.DataFrame(rows).T.rename_axis("year")


# Decision-relevant risks. Thresholds are rules of thumb, so their evidence is ASSUMED:
# check them with OMAFRA guidance or an agronomist before trusting a recommendation.
RISKS = {
    "late_spring_frost": ("last_spring_frost_doy", ">", 140, "a frost after 20 May (young corn/soy damage)"),
    "early_fall_frost": ("first_fall_frost_doy", "<", 273, "a frost before 30 September (immature soybean/corn)"),
    "pollination_heat": ("heat_days_pollination", ">=", 3, "3+ days at or above 32 degC during corn pollination"),
    "heavy_rain_on_bare_soil": ("heavy_rain_days_spring", ">=", 1, "a 25 mm+ rain day while fields are bare (15 Apr-15 Jun)"),
    "summer_dry_spell": ("longest_dry_spell_summer", ">=", 14, "2+ weeks without rain in June-August"),
    "short_fall_after_soybean": ("fall_gdd5_after_soybean", "<", 150,
                                 "too little fall warmth for a cover crop sown after soybean harvest (25 Sept)"),
    # DEPRECATED (Lesson 7): at Elora this never happened in 30 years, so it can't inform a decision.
    # Kept so profile readers written for schema 0.2 don't break; remove at schema 1.0.
    "short_fall_for_cover": ("fall_gdd5_sep_nov", "<", 300,
                             "(deprecated) too little fall warmth for a cover crop sown 1 Sept to establish"),
}


def uninformative_risks(counts, low=0.03, high=0.97):
    """Risks that (almost) never or (almost) always happen. A risk that never varies
    can't help choose between options: check its threshold before showing it."""
    return [k for k, c in counts.items() if c["of"] and not (low <= c["count"] / c["of"] <= high)]
_OPS = {">": np.greater, ">=": np.greater_equal, "<": np.less, "<=": np.less_equal}


def risk_counts(table, risks=None):
    """For each risk: how many rows (years or futures) cross the threshold."""
    risks = risks or RISKS
    out = {}
    for name, (col, op, thr, text) in risks.items():
        hit = _OPS[op](table[col].values, thr)
        out[name] = {"count": int(np.nansum(hit)), "of": int(table[col].notna().sum()), "text": text}
    return out


# ---------------------------------------------------------------- trend
def warming_trend(annual_mean, n_boot=2000, seed=0):
    """Linear trend in degC per year, with a 90% bootstrap confidence interval.

    Bootstrap: resample the (year, temperature) pairs with replacement, refit the slope,
    repeat 2000 times; the middle 90% of slopes is the interval. No normality assumption.
    """
    x, y = annual_mean.index.values.astype(float), annual_mean.values
    slope = np.polyfit(x, y, 1)[0]
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = rng.integers(0, len(x), len(x))
        if np.ptp(x[i]) > 0:
            boots.append(np.polyfit(x[i], y[i], 1)[0])
    lo, hi = np.percentile(boots, [5, 95])
    return {"slope_per_year": float(slope), "low": float(lo), "high": float(hi)}


# ---------------------------------------------------------------- futures
def make_futures(daily, n=100, target_year=2026, temp_trend=0.0, rain_sd=0.10, temp_sd=0.0,
                 seed=42, temp_cols=("T2M", "T2M_MIN", "T2M_MAX"), rain="PRECIP_CORR", min_days=360):
    """n possible seasons for `target_year`.

    Each future: pick a past year (with replacement), shift its temperatures by
    temp_trend x (target_year - year) to today's warmth, multiply its rain by
    (1 + N(0, rain_sd)) and add N(0, temp_sd) degC: the remaining correction error.
    Returns one row per future: its source year, the perturbations, and all indicators.
    """
    rng = np.random.default_rng(seed)
    years = [y for y, d in daily.groupby(daily.index.year) if len(d) >= min_days]
    rows = []
    for i in range(n):
        y = int(rng.choice(years))
        d = daily[daily.index.year == y].copy()
        rain_factor = max(0.0, 1 + rng.normal(0, rain_sd))
        t_shift = temp_trend * (target_year - y) + rng.normal(0, temp_sd)
        d[rain] = d[rain] * rain_factor
        for c in temp_cols:
            d[c] = d[c] + t_shift
        rows.append({"future": i + 1, "source_year": y, "rain_factor": round(rain_factor, 3),
                     "temp_shift": round(t_shift, 3), **year_indicators(d, rain=rain)})
    return pd.DataFrame(rows).set_index("future")

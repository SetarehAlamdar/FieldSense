"""Phenology: what a field's greenness through the year says about what grew and when it was bare.

From Lesson 4, plus the field barcode.

Input everywhere: NDVI observations for one field, a DataFrame with columns
`date` and `ndvi` (one row per clear satellite look), as produced by `sources.hls`.

Thresholds (checked against the Elora rotation plots, 2015-2025):
  - Winter wheat peaks in June (day ~160-181); corn and soybean from late July (day 200+).
    Peak TIMING separates them; spring greenness alone can't (overwintered cover crops are
    green in spring too).
  - We look for the main peak only up to mid-August (day 227): later, a cover crop sown
    after wheat can out-green the wheat and hide its June peak.
  - Bare soil and crop residue sit around NDVI 0.2-0.3, so below 0.3 counts as "bare".
Because these thresholds were chosen at Elora, Elora is no longer an independent test of them.
"""
import numpy as np
import pandas as pd

BARE_BELOW = 0.30          # NDVI below this = bare soil or residue
GREEN_FROM = 0.40          # NDVI at or above this = clearly living cover
MAIN_SEASON = (135, 273)   # ~15 May to 30 Sep: the main summer crop season at Elora (day of year)
WHEAT_PEAK_BEFORE = 195    # peak before this day of year -> winter wheat


def prepare(obs):
    """Sort, merge same-day looks, add year/day-of-year and a 3-look rolling MEDIAN.

    Same-day looks (Landsat and Sentinel-2 both passing) are averaged.
    The rolling median removes single bad looks (a missed cloud edge) without blurring the curve.
    """
    d = obs.dropna(subset=["ndvi"]).copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    d = d.groupby("date", as_index=False)["ndvi"].mean().sort_values("date")
    d["year"] = d["date"].dt.year
    d["doy"] = d["date"].dt.dayofyear
    d["ndvi_smooth"] = d["ndvi"].rolling(3, center=True, min_periods=1).median()
    return d


def _window_mean(d, year, m1, d1, m2, d2):
    sel = d[(d["date"] >= pd.Timestamp(year, m1, d1)) & (d["date"] <= pd.Timestamp(year, m2, d2))]
    return sel["ndvi"].mean() if len(sel) >= 2 else np.nan


def season_features(d_year):
    """A few numbers that summarise one field's season (input: prepared rows for ONE year)."""
    y = int(d_year["date"].dt.year.iloc[0])
    main = d_year[(d_year["doy"] >= 152) & (d_year["doy"] <= 227)]          # 1 Jun - mid Aug
    peak = main.loc[main["ndvi_smooth"].idxmax()] if len(main) else None
    return {
        "year": y,
        "n_obs": int(len(d_year)),
        "spring_green": _window_mean(d_year, y, 4, 1, 5, 20),
        "fall_green": _window_mean(d_year, y, 10, 1, 11, 30),
        "peak_ndvi": float(main["ndvi_smooth"].max()) if len(main) else np.nan,
        "peak_doy": float(peak["doy"]) if peak is not None else np.nan,
        "summer_mean": _window_mean(d_year, y, 6, 1, 9, 15),
    }


def crop_label(f):
    """Rough crop label from season features. Corn vs soybean is left joined on purpose:
    greenness alone can't separate them reliably, and the farmer can simply tell us."""
    if f["peak_doy"] is None or np.isnan(f["peak_doy"]):
        return "too few clear images"
    if f["peak_doy"] < WHEAT_PEAK_BEFORE:
        label = "winter wheat"
    elif f["peak_ndvi"] < 0.55:
        return "low cover / unclear"
    else:
        label = "corn or soybean"
    extras = []
    if label != "winter wheat" and f["spring_green"] >= 0.35:
        extras.append("green in spring (overwintered cover crop?)")
    if f["fall_green"] >= 0.5:
        extras.append("green after harvest (cover crop?)")
    return label + (" + " + ", ".join(extras) if extras else "")


def field_history(obs):
    """One row per year: season features plus the satellite's rough crop label."""
    d = prepare(obs)
    rows = [season_features(g) for _, g in d.groupby("year")]
    hist = pd.DataFrame(rows)
    hist["satellite_says"] = hist.apply(crop_label, axis=1)
    hist["green_off_season"] = hist[["spring_green", "fall_green"]].mean(axis=1)
    return hist


def daily_ndvi(obs, max_gap_days=30):
    """A value for every day, by straight-line interpolation between clear looks.

    Days inside a gap longer than `max_gap_days` (cloudy spells, winter snow) stay MISSING:
    we never invent greenness across weeks we did not see.
    """
    d = prepare(obs).set_index("date")["ndvi_smooth"]
    days = pd.date_range(d.index.min(), d.index.max(), freq="D")
    s = d.reindex(d.index.union(days)).interpolate(method="time").reindex(days)
    obs_dates = d.index.values
    nxt = np.searchsorted(obs_dates, days.values, side="left")
    prv = np.clip(nxt - 1, 0, len(obs_dates) - 1)
    nxt = np.clip(nxt, 0, len(obs_dates) - 1)
    gap = (obs_dates[nxt] - obs_dates[prv]) / np.timedelta64(1, "D")
    on_obs = np.isin(days.values, obs_dates)
    s[(gap > max_gap_days) & ~on_obs] = np.nan
    return s


def barcode_matrix(daily):
    """The field barcode: one row per year, one column per day of year (1-365), values = NDVI.

    29 February is dropped so every year has exactly 365 columns.
    """
    s = daily[~((daily.index.month == 2) & (daily.index.day == 29))]
    doy = s.index.dayofyear - ((s.index.is_leap_year) & (s.index.month > 2)).astype(int)
    frame = pd.DataFrame({"year": s.index.year, "doy": doy, "ndvi": s.values})
    return frame.pivot(index="year", columns="doy", values="ndvi").reindex(columns=range(1, 366))


def cover_summary(matrix, season=(60, 334)):
    """Per year, between ~1 March and 30 November (snow hides winter):
    observed_days, bare_days (NDVI < 0.30), green_days (>= 0.40), and
    green_days_off_season: living cover OUTSIDE the main summer crop season,
    the soil-health signal (cover crops, winter wheat).
    Days inside long cloud gaps are not counted at all, so compare SHARES
    (green_share_off_season = green / observed off-season days), not raw counts."""
    cols = [c for c in matrix.columns if season[0] <= c <= season[1]]
    off = [c for c in cols if not (MAIN_SEASON[0] <= c <= MAIN_SEASON[1])]
    m = matrix[cols]
    return pd.DataFrame({
        "observed_days": m.notna().sum(axis=1),
        "bare_days": (m < BARE_BELOW).sum(axis=1),
        "green_days": (m >= GREEN_FROM).sum(axis=1),
        "observed_days_off_season": matrix[off].notna().sum(axis=1),
        "green_days_off_season": (matrix[off] >= GREEN_FROM).sum(axis=1),
    }).assign(green_share_off_season=lambda t: (t.green_days_off_season /
                                                t.observed_days_off_season.where(t.observed_days_off_season > 0)).round(3))

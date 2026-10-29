"""Bias correction: make a model's rainfall match ground truth, month by month.

From Lesson 2. NASA POWER rainfall at Elora was ~25% too low. We multiply each day
by its calendar month's factor:

    factor[July] = station's average July rain / POWER's average July rain  (same months)

This shifts the LEVEL of rainfall but keeps the PATTERN (which years were dry or wet),
and the pattern is what the climate futures are built from.

Key lesson: a correction always matches the data it was fitted on, so that proves
only that the code works. Validation needs held-out years (fit 1996-2010, test 2011-2025).
"""
import pandas as pd


def factors_from(station_months, model_months):
    """One factor per calendar month from two monthly series with the same (year, month) index."""
    return station_months.groupby(level=1).mean() / model_months.groupby(level=1).mean()


def monthly_scaling_factors(model_series, reference_monthly_totals, start_year, end_year):
    """Factors from published monthly normals (12 numbers, Jan..Dec), same years as the normals."""
    s = model_series[(model_series.index.year >= start_year) & (model_series.index.year <= end_year)]
    model_mean = s.groupby([s.index.year, s.index.month]).sum().groupby(level=1).mean()
    ref = pd.Series(reference_monthly_totals, index=range(1, 13))
    return ref / model_mean


def apply_monthly_scaling(daily_series, factors):
    """Multiply each day's value by its calendar month's factor (factors indexed 1..12)."""
    return daily_series * daily_series.index.month.map(factors).values


def held_out_error(station_months, model_months, split_year):
    """Fit factors on years <= split_year, test on later years.

    Returns (raw_error_pct, corrected_error_pct) on the test years: the honest check.
    """
    years = station_months.index.get_level_values(0)
    train, test = years <= split_year, years > split_year
    f = factors_from(station_months[train], model_months[train])
    pred = model_months[test] * model_months[test].index.get_level_values(1).map(f).values
    obs = station_months[test].mean()
    return 100 * (model_months[test].mean() / obs - 1), 100 * (pred.mean() / obs - 1)

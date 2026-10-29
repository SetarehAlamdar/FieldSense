"""NASA POWER: daily weather for any point on Earth, 1981 to near-present.

From Lesson 1. POWER is a model-based product (MERRA-2 weather reanalysis + CERES
satellite sunshine) on a ~0.5 x 0.625 degree grid (~50 km). Good for climate
patterns; too coarse to tell neighbouring fields apart.

Every download is cached as a CSV, so the second call is instant and a live
demo never waits on NASA's servers.
"""
import os

import pandas as pd
import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Variables the crop and soil models use, with their units in the AG community
DEFAULT_PARAMETERS = {
    "T2M": "Mean air temperature at 2 m (degC)",
    "T2M_MAX": "Max air temperature (degC)",
    "T2M_MIN": "Min air temperature (degC)",
    "PRECTOTCORR": "Precipitation, bias-corrected by NASA (mm/day)",
    "ALLSKY_SFC_SW_DWN": "Solar radiation at the surface (MJ/m2/day)",
    "RH2M": "Relative humidity at 2 m (%)",
    "WS2M": "Wind speed at 2 m (m/s)",
}


def get_power_daily(lat, lon, start, end, parameters=None, cache_dir="data_cache"):
    """Daily NASA POWER weather for one point, as a DataFrame indexed by date.

    start, end: "YYYYMMDD" strings. NASA's missing-value code (-999) becomes NaN.
    """
    parameters = list(parameters or DEFAULT_PARAMETERS)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"power_{lat}_{lon}_{start}_{end}.csv")
    if os.path.exists(cache_file):
        return pd.read_csv(cache_file, index_col="date", parse_dates=True)

    params = {"parameters": ",".join(parameters), "community": "AG",
              "longitude": lon, "latitude": lat, "start": start, "end": end, "format": "JSON"}
    r = requests.get(POWER_URL, params=params, timeout=120)
    r.raise_for_status()
    table = pd.DataFrame(r.json()["properties"]["parameter"])   # outer keys -> columns, dates -> rows
    table.index = pd.to_datetime(table.index, format="%Y%m%d")
    table.index.name = "date"
    table = table.replace(-999, float("nan"))
    table.to_csv(cache_file)
    return table


def fill_small_gaps(df, max_days=3):
    """Fill gaps of up to `max_days` by straight-line interpolation; longer gaps stay missing."""
    return df.interpolate(method="time", limit=max_days, limit_area="inside")

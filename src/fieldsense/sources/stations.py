"""Environment and Climate Change Canada (ECCC) weather stations: ground truth for NASA POWER.

From Lesson 2. We used two stations near Elora:
  - Fergus Shand Dam (ID 4760): long manual record, the reference for the rainfall correction
  - Elora RCS (ID 41983): automatic Reference Climate Station, 2003-today, used as a cross-check

Lesson learned: ground truth has errors too. Elora RCS reads ~12% lower than Fergus,
mostly in winter, likely because automatic gauges under-catch blowing snow.
"""
import io
import os

import pandas as pd
import requests

BULK_URL = "https://climate.weather.gc.ca/climate_data/bulk_data_e.html"


def get_eccc_daily_precip(station_id, year):
    """One year of daily total precipitation (mm) from ECCC's bulk CSV service."""
    url = f"{BULK_URL}?format=csv&stationID={station_id}&Year={year}&Month=1&Day=1&timeframe=2&submit=Download+Data"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.content.decode("utf-8-sig")))
    precip_col = [c for c in df.columns if c.startswith("Total Precip")][0]
    return pd.Series(pd.to_numeric(df[precip_col], errors="coerce").values,
                     index=pd.to_datetime(df["Date/Time"]), name="station_mm")


def get_eccc_precip_years(station_id, first_year, last_year, cache_dir="data_cache"):
    """Daily precipitation for a range of years, downloaded once and cached as CSV."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"eccc_{station_id}_daily_{first_year}_{last_year}.csv")
    if os.path.exists(cache_file):
        return pd.read_csv(cache_file, index_col=0, parse_dates=True)["station_mm"]
    s = pd.concat([get_eccc_daily_precip(station_id, y) for y in range(first_year, last_year + 1)])
    s.to_csv(cache_file)
    return s


def good_monthly(daily, min_cover=0.9):
    """Monthly totals, keeping only months where at least `min_cover` of days were reported.

    A month with 10 missing days would look artificially dry; we drop it instead.
    """
    g = daily.groupby([daily.index.year, daily.index.month])
    ok = (g.count() / g.size()) >= min_cover
    return g.sum()[ok]

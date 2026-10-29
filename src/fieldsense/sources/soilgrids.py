"""SoilGrids (ISRIC): global soil properties at 250 m, with uncertainty.

From Lesson 2. SoilGrids is itself a machine-learning PREDICTION (trained on ~240,000
soil profiles), so each property comes with a 90% range (Q0.05 to Q0.95).
At Elora the organic-carbon range was very wide (an ~8x spread), likely a mixed
250 m pixel. That is why the product lets farmers override with a lab soil test.
"""
import os

import pandas as pd
import requests

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
DEFAULT_PROPERTIES = ["clay", "sand", "silt", "soc", "phh2o", "bdod"]
TOPSOIL_DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}       # layer -> thickness (cm)


def get_soilgrids(lat, lon, properties=None, depths=None, values=("mean", "Q0.05", "Q0.95"),
                  cache_dir="data_cache"):
    """Soil properties at one point, in conventional units, as a long table:
    property, depth, statistic, value, unit. Cached as CSV."""
    properties = properties or DEFAULT_PROPERTIES
    depths = depths or list(TOPSOIL_DEPTHS)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"soilgrids_{lat}_{lon}.csv")
    if os.path.exists(cache_file):
        return pd.read_csv(cache_file)
    params = [("lon", lon), ("lat", lat)]
    params += [("property", p) for p in properties]
    params += [("depth", d) for d in depths]
    params += [("value", v) for v in values]
    r = requests.get(SOILGRIDS_URL, params=params, timeout=120)
    r.raise_for_status()
    rows = []
    for layer in r.json()["properties"]["layers"]:
        units = layer["unit_measure"]
        factor = units["d_factor"]                 # values are stored as scaled integers
        for d in layer["depths"]:
            for stat, v in d["values"].items():
                rows.append({"property": layer["name"], "depth": d["label"], "statistic": stat,
                             "value": None if v is None else v / factor, "unit": units["target_units"]})
    table = pd.DataFrame(rows)
    table.to_csv(cache_file, index=False)
    return table


def topsoil_summary(soil_table):
    """Thickness-weighted 0-30 cm value of each property as {"low", "mid", "high"}.

    mid = weighted mean of the layer means; low/high = weighted Q0.05 / Q0.95.
    (Averaging percentiles across layers is an approximation; it is fine for a summary.)
    """
    t = soil_table.copy()
    t["w"] = t["depth"].map(TOPSOIL_DEPTHS)
    t = t.dropna(subset=["w", "value"])
    out = {}
    for prop, g in t.groupby("property"):
        vals = {}
        for stat, key in [("Q0.05", "low"), ("mean", "mid"), ("Q0.95", "high")]:
            s = g[g["statistic"] == stat]
            vals[key] = float((s["value"] * s["w"]).sum() / s["w"].sum()) if len(s) else None
        out[prop] = vals
    return out


def carbon_stock_t_ha(soc_g_kg, bulk_density_kg_dm3, depth_cm=30):
    """Soil organic carbon stock (t C/ha) = SOC (g/kg) x bulk density (kg/dm3) x depth (cm) x 0.1."""
    return soc_g_kg * bulk_density_kg_dm3 * depth_cm * 0.1


def usda_texture_class(sand, silt, clay):
    """USDA soil texture class from sand/silt/clay percentages (standard NRCS rules)."""
    if silt + 1.5 * clay < 15: return "sand"
    if silt + 2 * clay < 30: return "loamy sand"
    if (7 <= clay < 20 and sand > 52) or (clay < 7 and silt < 50): return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52: return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12): return "silt loam"
    if silt >= 80 and clay < 12: return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45: return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45: return "clay loam"
    if 27 <= clay < 40 and sand <= 20: return "silty clay loam"
    if clay >= 35 and sand > 45: return "sandy clay"
    if clay >= 40 and silt >= 40: return "silty clay"
    return "clay"

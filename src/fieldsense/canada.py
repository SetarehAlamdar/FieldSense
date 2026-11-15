"""FieldSense across Canada: the same measurements in five farming regions, checked in each.

Three things make the method work outside Elora:
1. A rotation rule for all of Canada (`rotation_group`): "simple" = at most two different
   crops in the recent years and no forage; "diverse" = three or more crops, or forage/hay
   inside an annual rotation. Corn-soybean and canola-wheat are both "simple".
2. A crop reading that does not depend on the crop list (`timing_class`): the satellite
   greenness curve says WHEN a field is green, which separates winter cereals, spring-sown
   crops, summer crops, forage and fallow. Each region checks this against the AAFC crop map.
3. Soil cover measured the same way everywhere (`cover_numbers`): shares of observed days,
   so cloud and snow gaps never count as bare soil.

`scorecard` puts it together per region, with a field-level bootstrap interval for the
difference between diverse and simple rotations.
"""
import numpy as np

from .phenology import BARE_BELOW, GREEN_FROM, MAIN_SEASON

# Five farming regions, west to east. Fields are found automatically within 5 km of each point.
REGIONS = {
    "ab": {"name": "Alberta", "place": "Central Alberta, near Lacombe", "lon": -113.70, "lat": 52.45,
           "system": "barley, canola, wheat, forage"},
    "sk": {"name": "Saskatchewan", "place": "Near Saskatoon", "lon": -106.35, "lat": 51.95,
           "system": "wheat, canola, pulses, fallow"},
    "mb": {"name": "Manitoba", "place": "Red River Valley, near Carman", "lon": -97.95, "lat": 49.50,
           "system": "canola, wheat, soybean, corn, oats"},
    "on": {"name": "Ontario", "place": "Wellington County, near Elora", "lon": -80.41, "lat": 43.64,
           "system": "corn, soybean, winter wheat"},
    "qc": {"name": "Quebec", "place": "Montérégie, near Saint-Hyacinthe", "lon": -72.95, "lat": 45.62,
           "system": "corn, soybean, cereals, hay"},
}

# AAFC Annual Crop Inventory codes -> (crop, growth-timing class)
WINTER, SPRING, SUMMER, FORAGE, FALLOW = "winter cereal", "spring crop", "summer crop", "forage", "fallow"
CROPS = {
    145: ("winter wheat", WINTER), 137: ("fall rye", WINTER),
    146: ("spring wheat", SPRING), 133: ("barley", SPRING), 136: ("oats", SPRING), 132: ("cereals", SPRING),
    134: ("other grains", SPRING), 139: ("triticale", SPRING), 153: ("canola", SPRING), 154: ("flax", SPRING),
    155: ("mustard", SPRING), 162: ("peas", SPRING), 163: ("chickpeas", SPRING), 168: ("faba beans", SPRING),
    174: ("lentils", SPRING), 196: ("canaryseed", SPRING),
    147: ("corn", SUMMER), 158: ("soybean", SUMMER), 167: ("dry beans", SUMMER), 157: ("sunflower", SUMMER),
    177: ("potatoes", SUMMER), 178: ("sugar beets", SUMMER), 195: ("buckwheat", SUMMER),
    122: ("pasture/forage", FORAGE),
    131: ("fallow", FALLOW),
}
CLASSES = [WINTER, SPRING, SUMMER, FORAGE, FALLOW]


def crop_name(code):
    return CROPS.get(int(code), (f"other ({int(code)})", None))[0]


def crop_class(code):
    return CROPS.get(int(code), (None, None))[1]


def rotation_group(seq, recent=5, min_known=0.8):
    """'simple', 'diverse' or None for a field's yearly crop codes (oldest first).

    Uses the `recent` latest years. At least `min_known` of them must be crops we know.
    Forage every year is permanent grassland, not a rotation (None).
    """
    s = [int(c) for c in seq[-recent:] if c]
    known = [c for c in s if c in CROPS]
    if not s or len(known) < min_known * len(s):
        return None
    classes = [crop_class(c) for c in known]
    if all(c == FORAGE for c in classes):
        return None
    has_forage = FORAGE in classes
    distinct = len({crop_name(c) for c in known})
    if distinct >= 3 or has_forage:
        return "diverse"
    if distinct == 2 or (distinct == 1 and classes[0] != FORAGE):
        return "simple"
    return None


# ------------------------------------------------------------------ reading the growth timing
def _mean(row, a, b):
    v = row[a - 1:b]
    v = v[np.isfinite(v)]
    return float(v.mean()) if v.size >= 3 else np.nan


def timing_class(row):
    """Growth-timing class of one field-year from its daily greenness (365 values, NaN = not seen).

    winter cereal: green early (May) and finished by August
    forage:        green early and still green in August
    spring crop:   not green in early May, peaks before ~27 July (day 208)
    summer crop:   not green in early May, peaks on or after day 208
    fallow:        never clearly green
    Returns None when there are too few clear days to tell.
    """
    row = np.asarray(row, dtype=float)
    season = row[99:270]                                  # 10 Apr - 27 Sep
    if np.isfinite(season).sum() < 40:
        return None
    peak = np.nanmax(season)
    if peak < 0.45:
        return FALLOW
    early = _mean(row, 125, 145)                          # ~5-25 May
    late = _mean(row, 215, 245)                           # ~3 Aug - 2 Sep
    peak_doy = 100 + int(np.nanargmax(season))
    if np.isfinite(early) and early >= GREEN_FROM:
        if np.isfinite(late) and late >= GREEN_FROM:
            return FORAGE
        return WINTER
    return SPRING if peak_doy < 208 else SUMMER


# ------------------------------------------------------------------ soil cover, measured
def cover_numbers(matrix_rows, season=(60, 334), spring=(105, 166)):
    """Soil cover from daily greenness rows (one per year, 365 values), as shares of OBSERVED days:
    bare_share_season (NDVI < 0.30 in 1 Mar - 30 Nov), spring_bare_share (not green, 15 Apr - 15 Jun)
    and green_share_off_season (green outside 15 May - 30 Sep)."""
    m = np.atleast_2d(np.asarray(matrix_rows, dtype=float))
    doy = np.arange(1, m.shape[1] + 1)
    ins = (doy >= season[0]) & (doy <= season[1])
    off = ins & ~((doy >= MAIN_SEASON[0]) & (doy <= MAIN_SEASON[1]))
    spr = (doy >= spring[0]) & (doy <= spring[1])

    def share(mask, test):
        v = m[:, mask]
        v = v[np.isfinite(v)]
        return float(test(v).mean()) if v.size else float("nan")

    return {"bare_share_season": share(ins, lambda v: v < BARE_BELOW),
            "spring_bare_share": share(spr, lambda v: v < GREEN_FROM),
            "green_share_off_season": share(off, lambda v: v >= GREEN_FROM)}


# ------------------------------------------------------------------ one region's scorecard
def field_record(field_id, name, group, crops_by_year, matrix):
    """Everything the page and the scorecard need for one field.

    crops_by_year: {year: ACI code}; matrix: pandas DataFrame, index = year, 365 daily columns.
    """
    years = [int(y) for y in matrix.index]
    rows = {y: matrix.loc[y].values.astype(float) for y in years}
    check = []
    for y in years:
        code = crops_by_year.get(y)
        truth = crop_class(code) if code is not None else None
        seen = timing_class(rows[y])
        if truth and seen:
            check.append({"year": y, "map": crop_name(code), "map_class": truth, "satellite_class": seen,
                          "agree": truth == seen})
    vals = np.round(np.vstack([rows[y] for y in years]) * 100)
    return {"id": int(field_id), "name": name, "group": group,
            "crops": {int(y): crop_name(c) for y, c in crops_by_year.items()},
            "cover": {k: round(v, 3) for k, v in cover_numbers([rows[y] for y in years]).items()},
            "check": check,
            "barcode": {"years": years, "scale": 100,
                        "values": [[None if not np.isfinite(v) else int(v) for v in r] for r in vals]}}


def _boot_diff(simple, diverse, n=2000, seed=2026, level=0.90):
    """Diverse minus simple mean, with a bootstrap interval that resamples FIELDS."""
    s, d = np.asarray(simple, float), np.asarray(diverse, float)
    s, d = s[np.isfinite(s)], d[np.isfinite(d)]
    if len(s) < 2 or len(d) < 2:
        return None
    rng = np.random.default_rng(seed)
    boots = rng.choice(d, (n, len(d))).mean(axis=1) - rng.choice(s, (n, len(s))).mean(axis=1)
    lo, hi = np.quantile(boots, [(1 - level) / 2, 1 - (1 - level) / 2])
    return {"diff": round(float(d.mean() - s.mean()), 3), "lo": round(float(lo), 3), "hi": round(float(hi), 3)}


# Set before looking at any region's results: crop timing is "validated" in a region when
# at least 80% of field-years agree with the crop map, with at least 15 field-years checked.
VALIDATED_FROM, MIN_CHECKS = 0.80, 15


def scorecard(region_key, fields):
    """One region's results from its field records."""
    checks = [c for f in fields for c in f["check"]]
    n_ok = sum(c["agree"] for c in checks)
    acc = n_ok / len(checks) if checks else None
    by_class = {}
    for c in checks:
        b = by_class.setdefault(c["map_class"], [0, 0])
        b[0] += c["agree"]
        b[1] += 1
    g = {k: [f for f in fields if f["group"] == k] for k in ("simple", "diverse")}
    cover = {}
    for k in ("bare_share_season", "spring_bare_share", "green_share_off_season"):
        sv = [f["cover"][k] for f in g["simple"]]
        dv = [f["cover"][k] for f in g["diverse"]]
        cover[k] = {"simple": round(float(np.nanmean(sv)), 3) if sv else None,
                    "diverse": round(float(np.nanmean(dv)), 3) if dv else None,
                    "diff": _boot_diff(sv, dv)}
    label = ("validated" if acc is not None and len(checks) >= MIN_CHECKS and acc >= VALIDATED_FROM
             else "not validated")
    return {"region": region_key, **REGIONS[region_key],
            "lon": round(REGIONS[region_key]["lon"], 2), "lat": round(REGIONS[region_key]["lat"], 2),
            "n_simple": len(g["simple"]), "n_diverse": len(g["diverse"]),
            "timing": {"agree": n_ok, "checked": len(checks), "share": round(acc, 3) if acc is not None else None,
                       "by_class": {k: {"agree": v[0], "checked": v[1]} for k, v in by_class.items()},
                       "evidence": label},
            "cover": cover}


# ------------------------------------------------------------------ running one region (Colab)
def find_region_fields(region_key, cache_dir, aci_years=range(2019, 2026), half_size_m=5000, max_per_group=4):
    """Fields in a 10 x 10 km square around the region's point, from the AAFC crop map.

    Tries smaller fields if it finds fewer than two of either kind. Returns (fields, epsg, box);
    each field has "lonlat" (its outline: keep it private), "codes" and "crops" per year.
    """
    from .sources import aci
    r = REGIONS[region_key]
    years = list(aci_years)
    epsg, box = aci.box_around(r["lon"], r["lat"], half_size_m)
    stack = np.stack([aci.get_aci(y, epsg, box, cache_dir=cache_dir) for y in years])
    names = {c: v[0] for c, v in CROPS.items()}
    fields = []
    for min_ha, purity in [(20, 0.7), (12, 0.65), (6, 0.6)]:
        fields = aci.find_fields(stack, years, epsg, box, min_ha=min_ha, purity=purity, max_per_group=max_per_group,
                                 grouper=rotation_group, names=names)
        n = {g: sum(f["group"] == g for f in fields) for g in ("simple", "diverse")}
        print(f"  min {min_ha} ha, purity {purity}: {n}")
        if n["simple"] >= 2 and n["diverse"] >= 2:
            break
    for i, f in enumerate(fields, start=1):
        f["id"], f["name"] = i, f"{r['name']} field {'ABCDEFGH'[i - 1]}"
    return fields, epsg, box


def hls_ndvi_for_fields(fields_lonlat, out_csv, start="2021-01-01", end="2025-12-31", workers=16, batch=50):
    """Average greenness inside each field for every HLS image, saved to `out_csv` as it goes.

    Run it again after a disconnect: images already in the file are skipped.
    """
    import concurrent.futures as cf
    import os
    import time

    import earthaccess
    import pandas as pd

    from .sources import hls
    lons = [p[0] for ring in fields_lonlat.values() for p in ring]
    lats = [p[1] for ring in fields_lonlat.values() for p in ring]
    bbox = (min(lons) - 0.005, min(lats) - 0.005, max(lons) + 0.005, max(lats) + 0.005)
    rows = []
    for short_name in ("HLSL30", "HLSS30"):
        for g in earthaccess.search_data(short_name=short_name, version="2.0", bounding_box=bbox,
                                         temporal=(start, end), cloud_cover=(0, 80), count=-1):
            info = hls.granule_info(g["meta"]["native-id"])
            info["links"] = hls.band_links(g.data_links(), info["sensor"])
            if info["links"]:
                rows.append(info)
    if not rows:
        print("  no HLS images found")
        return
    catalog = pd.DataFrame(rows)
    main_tile = catalog["tile"].value_counts().idxmax()
    catalog = catalog[catalog["tile"] == main_tile].sort_values("date").reset_index(drop=True)
    done = set(pd.read_csv(out_csv)["granule"]) if os.path.exists(out_csv) else set()
    todo = [r for _, r in catalog[~catalog["granule"].isin(done)].iterrows()]
    print(f"  tile {main_tile}: {len(catalog)} images, {len(done)} done, {len(todo)} to go")

    def work(row):
        try:
            res = hls.read_plot_ndvi(row["links"], fields_lonlat)
            return [{"granule": row["granule"], "date": row["date"].date(), "plot": fid, "ndvi": v[0],
                     "n_valid": v[1], "n_pixels": v[2]} for fid, v in res.items()]
        except Exception as e:
            return {"granule": row["granule"], "error": f"{type(e).__name__}: {str(e)[:100]}"}

    failures, t0 = [], time.time()
    for s in range(0, len(todo), batch):
        part = todo[s:s + batch]
        with cf.ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(work, part))
        good = [x for r in results if isinstance(r, list) for x in r]
        failures += [r for r in results if isinstance(r, dict)]
        if good:
            pd.DataFrame(good).to_csv(out_csv, mode="a", header=not os.path.exists(out_csv), index=False)
        print(f"  {s + len(part)}/{len(todo)} images | {time.time() - t0:.0f} s | failures: {len(failures)}")
    if failures:
        print(f"  {len(failures)} images failed: run the cell again to retry them")


def region_records(ndvi, fields, years=range(2021, 2026)):
    """Field records (see `field_record`) from the greenness table of one region."""
    from .phenology import barcode_matrix, daily_ndvi
    years = list(years)
    out = []
    for f in fields:
        obs = ndvi[(ndvi["plot"] == f["id"]) & ndvi["ndvi"].notna()][["date", "ndvi"]]
        if len(obs) < 20:
            print(f"  {f['name']}: only {len(obs)} clear looks, skipped")
            continue
        m = barcode_matrix(daily_ndvi(obs))
        m = m[m.index.isin(years)]
        codes = {int(y): int(c) for y, c in f["codes"].items() if int(y) in years}
        out.append(field_record(f["id"], f["name"], f["group"], codes, m))
    return out


def export_canada(records_by_region, out_path):
    """Write the page's canada.json: one scorecard per region plus its fields (no outlines,
    no field coordinates; only each region's rounded centre point)."""
    import json

    from .export import check_public
    regions = []
    for key in REGIONS:                                  # west to east
        recs = records_by_region.get(key)
        if not recs:
            continue
        sc = scorecard(key, recs)
        sc["fields"] = [{k: v for k, v in r.items() if k != "check"} | {
            "timing_agree": sum(c["agree"] for c in r["check"]), "timing_checked": len(r["check"])} for r in recs]
        regions.append(sc)
    allf = [r for k in records_by_region for r in records_by_region[k]]
    pooled = scorecard(next(iter(records_by_region)), allf) if allf else None
    out = {"regions": regions,
           "all": {"timing": pooled["timing"], "cover": pooled["cover"],
                   "n_simple": pooled["n_simple"], "n_diverse": pooled["n_diverse"]} if pooled else None,
           "rule": f"Crop timing counts as validated in a region when at least {VALIDATED_FROM:.0%} of at least "
                   f"{MIN_CHECKS} field-years agree with the AAFC crop map (rule set before the results).",
           "source": "NASA HLS v2.0 greenness (30 m), AAFC Annual Crop Inventory"}
    problems = check_public(out)
    if problems:
        raise ValueError(f"not safe to publish: {problems[:5]}")
    with open(out_path, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    return out

"""FieldSense for one farmer's field: enter a location, get the field's history and a rotation choice.

1. `field_at_point`: the field AT the point, from the AAFC crop map: the connected area around the
   point that grew the same crop in each recent year. Its outline stays in the notebook (private).
2. Every clear NASA HLS image of it (2021-2025): barcode, crop timing checked against the map,
   soil cover (see `canada`).
3. Nearest Environment Canada station, corrected NASA POWER, 1,000 possible 2027 seasons (`anywhere`).
4. `rotation_advice`: the rotation engine (`rotation`), with the field's MEASURED cover for its
   current rotation. Its options and crop calendars are for Ontario-type corn-soybean-wheat systems,
   so for other systems (canola, spring cereals, pulses) it says so instead of guessing.
"""
import numpy as np

from . import canada as ca

EASTERN = {147, 158, 145}          # corn, soybean, winter wheat: the systems the rotation engine knows


def field_at_point(lon, lat, cache_dir, years=range(2019, 2026), half_size_m=1500, recent=5, min_ha=2):
    """The crop-map field that contains (lon, lat), or None (not farmland / too small).

    Returns {"lonlat", "area_ha", "codes", "crops", "purity", "group"}; group is "simple",
    "diverse" or None (by `canada.rotation_group`).
    """
    from pyproj import Transformer
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from scipy import ndimage
    from shapely.geometry import shape

    from .sources import aci
    years = list(years)
    epsg, box = aci.box_around(lon, lat, half_size_m)
    stack = np.stack([aci.get_aci(y, epsg, box, cache_dir=cache_dir) for y in years])
    smooth = np.stack([aci._mode3(a) for a in stack])
    keys = np.zeros(smooth.shape[1:], dtype=np.int64)
    for a in smooth[-recent:]:
        keys = keys * 256 + a.astype(np.int64)
    xmin, ymin, xmax, ymax = box
    x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(lon, lat)
    col, row = int((x - xmin) // aci.PIXEL_M), int((ymax - y) // aci.PIXEL_M)
    if not (0 <= row < keys.shape[0] and 0 <= col < keys.shape[1]):
        return None
    labels, _ = ndimage.label(keys == keys[row, col], structure=np.ones((3, 3)))
    comp = labels == labels[row, col]
    inner = ndimage.binary_erosion(comp, iterations=1)
    if inner.sum() * aci.PIXEL_M ** 2 / 10_000 >= min_ha:
        comp = inner                                     # drop mixed edge pixels when the field is big enough
    area = float(comp.sum() * aci.PIXEL_M ** 2 / 10_000)
    if area < min_ha:
        return None
    seq, pur = [], []
    for a in stack:
        vals, cnt = np.unique(a[comp], return_counts=True)
        seq.append(int(vals[cnt.argmax()]))
        pur.append(round(float(cnt.max() / cnt.sum()), 2))
    tr = from_origin(xmin, ymax, aci.PIXEL_M, aci.PIXEL_M)
    polys = [shape(g) for g, v in shapes(comp.astype("uint8"), mask=comp, transform=tr) if v == 1]
    poly = max(polys, key=lambda p: p.area).simplify(aci.PIXEL_M / 2)
    to_ll = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform
    return {"lonlat": [list(to_ll(px, py)) for px, py in poly.exterior.coords], "area_ha": round(area, 1),
            "codes": {int(yr): c for yr, c in zip(years, seq)},
            "crops": {int(yr): ca.crop_name(c) for yr, c in zip(years, seq)},
            "purity": {int(yr): p for yr, p in zip(years, pur)},
            "group": ca.rotation_group(seq)}


def rotation_advice(history, odds, measured_cover, codes):
    """Rotation choice and reasons for an Ontario-type field, or a clear 'not yet' otherwise.

    history: list of {"year", "satellite_says"} (phenology.field_history); odds: climate odds with
    risks[k]["share"]; measured_cover: {"green_share_off_season", "spring_bare_share"} of THIS field;
    codes: {year: crop-map code}.
    """
    from . import rotation as rt
    recent = [codes[y] for y in sorted(codes)][-5:]
    if sum(c in EASTERN for c in recent) < 4:
        return {"available": False,
                "reason": "This field grows crops the rotation options don't cover yet "
                          f"({', '.join(sorted({ca.crop_name(c) for c in recent}))}). Its history, soil cover and "
                          "2027 weather above are measured; rotation options for these crops are the next step."}
    table = rt.compare(rt.CANDIDATES, odds)
    robust = rt.rank_robustness(table)                    # share of 2,000 random priority mixes won
    current = rt.detect_current(history)
    best = str(robust.index[0])
    names = {r.key: r.name for r in rt.CANDIDATES}
    keys = [current] if best == current else [current, best]
    why = {k: rt.explain(table.loc[k], current, {"what": "validated" if k == current else "assumed",
                                                  "soil_cover": "measured" if k == current else "modelled",
                                                  "climate_2026": "assumed", "nutrients_pests": "assumed"},
                         measured_cover=measured_cover if k == current else None)
           for k in keys}
    return {"available": True, "current": current, "current_name": names[current],
            "suggested": best, "suggested_name": names[best], "keep": best == current,
            "next_crop_if_kept": rt.next_crop(current, history),
            "robustness": {names[k]: round(float(v), 3) for k, v in robust.items()},
            "table": table, "why": why}

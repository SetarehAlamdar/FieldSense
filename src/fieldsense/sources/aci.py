"""AAFC Annual Crop Inventory (ACI): Canada's national 30 m crop map, one per year.

Used two ways:
1. To FIND farm fields automatically: areas that grew the same crop, pixel by pixel,
   for several recent years are treated as one field.
2. As GROUND TRUTH at those fields: which crop each field grew each year, to test
   FieldSense's satellite crop history away from the Elora trial.

AAFC targets at least 85% accuracy for the map, so it is good, independent ground truth,
not perfect. It does not map cover crops.
Service: https://www.agr.gc.ca/imagery-images/rest/services/annual_crop_inventory/<year>/ImageServer
"""
import io
import os

import numpy as np
import requests

URL = "https://www.agr.gc.ca/imagery-images/rest/services/annual_crop_inventory/{year}/ImageServer/exportImage"
CROPS = {147: "corn", 158: "soybean", 145: "winter wheat", 146: "spring wheat", 133: "barley",
         136: "oats", 153: "canola", 122: "pasture/forage"}
CORN, SOY, WINTER_WHEAT = 147, 158, 145
SMALL_GRAINS = {145, 146, 133, 136}
PIXEL_M = 30


def utm_epsg(lon, lat):
    return (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1


def box_around(lon, lat, half_size_m):
    """Square box (xmin, ymin, xmax, ymax) in UTM metres around lon/lat, snapped to 30 m."""
    from pyproj import Transformer
    epsg = utm_epsg(lon, lat)
    x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(lon, lat)
    snap = lambda v: PIXEL_M * round(v / PIXEL_M)
    return epsg, (snap(x - half_size_m), snap(y - half_size_m), snap(x + half_size_m), snap(y + half_size_m))


def get_aci(year, epsg, box, cache_dir="data_cache"):
    """Crop codes for one year in `box` (UTM, metres) as a 2-D uint8 array, cached as .npy."""
    os.makedirs(cache_dir, exist_ok=True)
    xmin, ymin, xmax, ymax = box
    cache = os.path.join(cache_dir, f"aci_{year}_{epsg}_{int(xmin)}_{int(ymin)}_{int(xmax)}_{int(ymax)}.npy")
    if os.path.exists(cache):
        return np.load(cache)
    import rasterio
    w, h = int((xmax - xmin) / PIXEL_M), int((ymax - ymin) / PIXEL_M)
    params = {"bbox": f"{xmin},{ymin},{xmax},{ymax}", "bboxSR": epsg, "imageSR": epsg, "size": f"{w},{h}",
              "format": "tiff", "pixelType": "U8", "interpolation": "RSP_NearestNeighbor", "f": "image"}
    r = requests.get(URL.format(year=year), params=params, timeout=120)
    r.raise_for_status()
    with rasterio.open(io.BytesIO(r.content)) as src:
        arr = src.read(1)
    if arr.shape != (h, w):
        raise ValueError(f"ACI {year}: expected {(h, w)}, got {arr.shape}")
    np.save(cache, arr)
    return arr


def _mode3(a):
    """3x3 majority filter: removes single misclassified pixels without moving field edges much."""
    from scipy import ndimage
    vals = np.unique(a)
    counts = np.stack([ndimage.uniform_filter((a == v).astype("float32"), 3, mode="nearest") for v in vals])
    return vals[counts.argmax(axis=0)].astype(a.dtype)


def rotation_group(seq):
    """'simple' (corn and soybean only), 'diverse' (winter wheat twice or more, plus corn and soybean), or None."""
    s = [c for c in seq if c]
    if not s:
        return None
    crops = set(s)
    if crops <= {CORN, SOY} and CORN in crops and SOY in crops:
        return "simple"
    if s.count(WINTER_WHEAT) >= 2 and CORN in crops and SOY in crops and crops <= {CORN, SOY} | SMALL_GRAINS:
        return "diverse"
    return None


def find_fields(stack, years, epsg, box, recent=5, min_ha=20, purity=0.7, exclude=None, max_per_group=4,
                grouper=None, names=None):
    """Find farm fields in a stack of yearly crop maps.

    stack: array (years, H, W) of ACI codes. A field = connected pixels with the same
    (majority-filtered) crop in each of the `recent` latest years, shrunk by one pixel to
    drop mixed edge pixels. For every year, the field's crop is the majority crop inside it
    and `purity` is the share of pixels that agree. Fields need >= min_ha hectares, a clean
    record (purity >= `purity` in at least 80% of years) and a simple or diverse rotation.
    exclude: (lon, lat, radius_m) to skip, e.g. the research station itself.
    grouper: function(codes) -> "simple" | "diverse" | None (default: the Ontario rule above;
    `fieldsense.canada.rotation_group` works for all of Canada). names: {code: crop name}.
    Returns a list of dicts sorted by area, at most `max_per_group` per rotation group.
    """
    from pyproj import Transformer
    from rasterio.features import shapes
    from rasterio.transform import from_origin
    from scipy import ndimage
    from shapely.geometry import shape
    
    xmin, ymin, xmax, ymax = box
    tr = from_origin(xmin, ymax, PIXEL_M, PIXEL_M)
    smooth = np.stack([_mode3(a) for a in stack])
    rec = smooth[-recent:]
    # pixels whose recent crop sequence is identical to all 8 neighbours get one key per sequence
    keys = np.zeros(rec.shape[1:], dtype=np.int64)
    for a in rec:
        keys = keys * 256 + a.astype(np.int64)
    to_ll = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform
    if exclude:
        ex_x, ex_y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(exclude[0], exclude[1])
    min_px = min_ha * 10_000 / PIXEL_M ** 2
    found = []
    for key in np.unique(keys):
        mask = keys == key
        if mask.sum() < min_px:
            continue
        labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
        for lab in range(1, n + 1):
            comp = ndimage.binary_erosion(labels == lab, iterations=1)
            if comp.sum() < min_px:
                continue
            seq, pur = [], []
            for a in stack:
                vals, cnt = np.unique(a[comp], return_counts=True)
                seq.append(int(vals[cnt.argmax()]))
                pur.append(float(cnt.max() / cnt.sum()))
            if np.mean(np.array(pur) >= purity) < 0.8:
                continue
            group = (grouper or rotation_group)(seq)
            if not group:
                continue
            polys = [shape(g) for g, v in shapes(comp.astype("uint8"), mask=comp, transform=tr) if v == 1]
            poly = max(polys, key=lambda p: p.area).simplify(PIXEL_M / 2)
            c = poly.centroid
            if exclude and ((c.x - ex_x) ** 2 + (c.y - ex_y) ** 2) ** 0.5 < exclude[2]:
                continue
            found.append({"group": group, "area_ha": round(float(comp.sum() * PIXEL_M ** 2 / 10_000), 1),
                          "crops": {int(y): (names or CROPS).get(s, f"other ({s})") for y, s in zip(years, seq)},
                          "codes": {int(y): int(s) for y, s in zip(years, seq)},
                          "purity": {int(y): round(p, 2) for y, p in zip(years, pur)},
                          "lonlat": [list(to_ll(x, y)) for x, y in poly.exterior.coords]})
    out = []
    for g in ("simple", "diverse"):
        out += sorted([f for f in found if f["group"] == g], key=lambda f: -f["area_ha"])[:max_per_group]
    return out

"""Satellite views: small true-colour and greenness pictures of an area from NASA HLS.

For the website's "Seen from space" section. Unlike `hls.read_plot_ndvi` (which averages
pixels inside each plot), this reads a square around a point and returns it as an image.

Privacy: the square is centred on a rounded coordinate and drawn without plot outlines,
so it shows the landscape, not where any particular trial plot is.
"""
import json
import os

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window, from_bounds

from . import hls

SCALE = 0.0001          # HLS reflectance is stored as integers x 10,000
NODATA = -9999
# Same greenness colours as the barcode on the website: bare soil (brown) -> dense crop (green)
STOPS = [(0.1, (140, 90, 43)), (0.3, (217, 196, 140)), (0.5, (201, 221, 138)), (0.7, (90, 160, 64)), (0.9, (31, 107, 42))]
CLOUD_GREY = (226, 224, 217)


def view_links(urls, sensor):
    """Links to the red, green, blue, near-infrared and cloud-mask files of one granule."""
    wanted = {"red": "B04", "green": "B03", "blue": "B02", "nir": hls.NIR_BAND[sensor], "fmask": "Fmask"}
    out = {}
    for key, band in wanted.items():
        match = [u for u in urls if u.endswith(f".{band}.tif")]
        if match:
            out[key] = match[0]
    return out if len(out) == len(wanted) else None


def read_view(links, lon, lat, half_size_m=1500):
    """Read a square (2 x half_size_m wide) around lon/lat. Returns reflectances and a bad-pixel mask."""
    bands = {}
    with rasterio.Env(**hls.GDAL_OPTS):
        with hls._open(links["red"]) as src:
            x, y = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True).transform(lon, lat)
            w = from_bounds(x - half_size_m, y - half_size_m, x + half_size_m, y + half_size_m, transform=src.transform)
            win = Window(int(round(w.col_off)), int(round(w.row_off)), int(round(w.width)), int(round(w.height)))
            win = win.intersection(Window(0, 0, src.width, src.height))   # stay inside the image tile
            bands["red"] = src.read(1, window=win)
        for key in ("green", "blue", "nir", "fmask"):
            with hls._open(links[key]) as src:
                bands[key] = src.read(1, window=win)
    fmask = bands.pop("fmask")
    nodata = np.zeros(fmask.shape, bool)
    for b in bands.values():
        nodata |= b <= NODATA
    bad = nodata | (fmask == 255) | ((fmask & hls.BAD_FMASK_BITS) != 0)
    refl = {k: np.where(v <= NODATA, np.nan, v * SCALE).astype("float32") for k, v in bands.items()}
    return {**refl, "bad": bad, "bad_fraction": float(bad.mean())}


def true_colour(view, max_reflectance=0.18, gamma=0.8):
    """RGB picture as people would see it (uint8 H x W x 3). Clouds and gaps are grey."""
    rgb = np.dstack([view["red"], view["green"], view["blue"]])
    rgb = np.clip(np.nan_to_num(rgb) / max_reflectance, 0, 1) ** gamma
    out = (rgb * 255).astype("uint8")
    out[view["bad"]] = CLOUD_GREY
    return out


def greenness(view):
    """NDVI picture in the barcode colours (uint8 H x W x 3). Clouds and gaps are grey."""
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (view["nir"] - view["red"]) / (view["nir"] + view["red"])
    v = np.nan_to_num(ndvi, nan=0.0)
    xs = [s[0] for s in STOPS]
    out = np.dstack([np.interp(v, xs, [s[1][c] for s in STOPS]) for c in range(3)]).astype("uint8")
    out[view["bad"] | ~np.isfinite(ndvi)] = CLOUD_GREY
    return out


def _cloud_cover(granule):
    for a in granule["umm"].get("AdditionalAttributes", []):
        if a.get("Name") == "CLOUD_COVERAGE":
            try:
                return float(a["Values"][0])
            except (KeyError, IndexError, ValueError):
                pass
    return 100.0


def find_clear_views(lon, lat, windows, half_size_m=1500, max_bad=0.05, max_tries=6):
    """For each named date window, the clearest HLS view of the square around lon/lat.

    windows: {"Late May": ("2023-05-15", "2023-06-10"), ...}
    Tries up to `max_tries` granules per window (least cloudy first) and stops at the first
    one with at most `max_bad` cloudy or missing pixels in our square.
    Needs `earthaccess.login()` and `hls.use_earthaccess_login()` first.
    """
    import earthaccess
    bbox = (lon - 0.03, lat - 0.03, lon + 0.03, lat + 0.03)
    found = []
    for label, (start, end) in windows.items():
        results = earthaccess.search_data(short_name=["HLSL30", "HLSS30"], bounding_box=bbox,
                                          temporal=(start, end), cloud_cover=(0, 60))
        best = None
        for g in sorted(results, key=_cloud_cover)[:max_tries]:
            info = hls.granule_info(g["meta"]["native-id"])
            links = view_links(g.data_links(), info["sensor"])
            if not links:
                continue
            try:
                view = read_view(links, lon, lat, half_size_m)
            except Exception as err:            # one unreadable file shouldn't stop the others
                print(f"  skipped {info['granule']}: {err}")
                continue
            if best is None or view["bad_fraction"] < best["view"]["bad_fraction"]:
                best = {"label": label, "date": info["date"].strftime("%Y-%m-%d"), "sensor": info["sensor"], "view": view}
            if view["bad_fraction"] <= max_bad:
                break
        if best:
            print(f"{label}: {best['date']} ({best['sensor']}), {100 * best['view']['bad_fraction']:.0f}% cloudy or missing")
            found.append(best)
        else:
            print(f"{label}: no usable image found")
    return found


def save_views(found, out_dir, scale=4, half_size_m=1500, note=""):
    """Write space_<n>_true.png and space_<n>_green.png plus space.json for the website."""
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    entries = []
    for i, f in enumerate(found, start=1):
        names = {}
        for kind, make in (("true", true_colour), ("green", greenness)):
            img = Image.fromarray(make(f["view"]))
            img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
            names[kind] = f"space_{i}_{kind}.png"
            img.save(os.path.join(out_dir, names[kind]))
        entries.append({"label": f["label"], "date": f["date"], "sensor": f["sensor"],
                        "clear_share": round(1 - f["view"]["bad_fraction"], 3), **names})
    meta = {"views": entries, "size_km": round(2 * half_size_m / 1000, 1), "note": note,
            "source": "NASA HLS v2.0 (Landsat 8/9 L30 + Sentinel-2 S30), 30 m"}
    with open(os.path.join(out_dir, "space.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    return meta

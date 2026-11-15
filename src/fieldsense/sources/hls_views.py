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
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from shapely.geometry import mapping

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
                best = {"label": label, "date": info["date"].strftime("%Y-%m-%d"), "sensor": info["sensor"],
                        "view": view, "links": links}
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


# ------------------------------------------------------------------ one picture per plot
def read_plot_views(links, plots_lonlat, pad_px=1):
    """Each plot's own pixels from one granule: {plot_id: view}, where view["inside"]
    marks the pixels whose centre is inside the plot (everything else becomes transparent)."""
    out = {}
    with rasterio.Env(**hls.GDAL_OPTS):
        with hls._open(links["red"]) as src:
            geoms = hls.plots_in_crs(plots_lonlat, src.crs, inner_buffer_m=0)
            windows = {}
            for pid, g in geoms.items():
                minx, miny, maxx, maxy = g.bounds
                w = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
                win = Window(int(np.floor(w.col_off)) - pad_px, int(np.floor(w.row_off)) - pad_px,
                             int(np.ceil(w.width)) + 2 * pad_px + 1, int(np.ceil(w.height)) + 2 * pad_px + 1)
                windows[pid] = (win, src.window_transform(win))
            bands = {pid: {"red": src.read(1, window=win)} for pid, (win, _) in windows.items()}
        for key in ("green", "blue", "nir", "fmask"):
            with hls._open(links[key]) as src:
                for pid, (win, _) in windows.items():
                    bands[pid][key] = src.read(1, window=win)
    for pid, b in bands.items():
        win, tr = windows[pid]
        inside = geometry_mask([mapping(geoms[pid])], out_shape=b["red"].shape, transform=tr, invert=True)
        fmask = b.pop("fmask")
        nodata = np.zeros(fmask.shape, bool)
        for v in b.values():
            nodata |= v <= NODATA
        bad = nodata | (fmask == 255) | ((fmask & hls.BAD_FMASK_BITS) != 0)
        refl = {k: np.where(v <= NODATA, np.nan, v * SCALE).astype("float32") for k, v in b.items()}
        out[pid] = {**refl, "bad": bad, "inside": inside,
                    "bad_fraction": float(bad[inside].mean()) if inside.any() else 1.0}
    return out


def _with_alpha(rgb, inside):
    alpha = np.where(inside, 255, 0).astype("uint8")
    return np.dstack([rgb, alpha])


def add_plot_views(found, plots_lonlat, out_dir, designs=None, scale=24, key="plots", prefix="plot", names=None):
    """For the dates in `found` (from find_clear_views), save each plot's true-colour and
    greenness picture and add a table (rows = fields, columns = dates) to space.json under `key`
    ("plots" for the trial plots, "farms" for nearby farm fields)."""
    from PIL import Image
    designs = designs or {}
    rows = {pid: [] for pid in sorted(plots_lonlat)}
    for i, f in enumerate(found, start=1):
        views = read_plot_views(f["links"], plots_lonlat)
        for pid in rows:
            v = views[pid]
            tile = {}
            for kind, make in (("true", true_colour), ("green", greenness)):
                img = Image.fromarray(_with_alpha(make(v), v["inside"]), "RGBA")
                img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
                tile[kind] = f"{prefix}{pid}_{i}_{kind}.png"
                img.save(os.path.join(out_dir, tile[kind]))
            tile["clear_share"] = round(1 - v["bad_fraction"], 3)
            rows[pid].append(tile)
    path = os.path.join(out_dir, "space.json")
    meta = json.load(open(path)) if os.path.exists(path) else {"views": []}
    names = names or {}
    meta[key] = {
        "dates": [{"label": f["label"], "date": f["date"]} for f in found],
        "rows": [{"plot": int(pid), "name": names.get(pid, f"Plot {pid}"), "design": designs.get(pid, ""), "tiles": tiles}
                 for pid, tiles in rows.items()],
        "note": "Only each field's own 30 m pixels are shown; nothing outside the field.",
    }
    with open(path, "w") as fh:
        json.dump(meta, fh, indent=1)
    return meta


# ------------------------------------------------------------------ a year of pictures per field
def search_granules(bbox, start, end, max_cloud=80):
    """All HLS granules over `bbox` between two dates: [{"date", "sensor", "links"}], oldest first."""
    import earthaccess
    out = []
    for short_name in ("HLSL30", "HLSS30"):
        for g in earthaccess.search_data(short_name=short_name, version="2.0", bounding_box=bbox,
                                         temporal=(start, end), cloud_cover=(0, max_cloud), count=-1):
            info = hls.granule_info(g["meta"]["native-id"])
            links = view_links(g.data_links(), info["sensor"])
            if links:
                out.append({"date": info["date"].strftime("%Y-%m-%d"), "sensor": info["sensor"],
                            "tile": info["tile"], "links": links})
    if out:                                    # keep one tile so each date is counted once
        tiles = [g["tile"] for g in out]
        main = max(set(tiles), key=tiles.count)
        out = [g for g in out if g["tile"] == main]
    return sorted(out, key=lambda g: g["date"])


def add_field_timeline(granules, fields_lonlat, out_dir, year, designs=None, names=None, files=None,
                       max_bad=0.1, scale=6):
    """Every clear picture of each field through one year, for the page's "Watch a year" animation.

    granules: from `search_granules` (one year). A picture is kept when at most `max_bad`
    of the field's pixels are cloudy or missing. Saves timeline.json, with the pictures packed inside it. Only pixels inside each field are drawn;
    everything else is transparent.
    """
    import base64
    import io
    from PIL import Image
    designs, names, files = designs or {}, names or {}, files or {}
    frames = {fid: [] for fid in fields_lonlat}
    for g in granules:
        try:
            views = read_plot_views(g["links"], fields_lonlat)
        except Exception as err:
            print(f"  skipped {g['date']}: {err}")
            continue
        for fid, v in views.items():
            if v["bad_fraction"] > max_bad or (frames[fid] and frames[fid][-1]["date"] == g["date"]):
                continue
            entry = {"date": g["date"], "clear": round(1 - v["bad_fraction"], 3)}
            for kind, make in (("true", true_colour), ("green", greenness)):
                img = Image.fromarray(_with_alpha(make(v), v["inside"]), "RGBA")
                img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                # packed inside timeline.json: one file instead of hundreds (GitHub's web upload takes 100 at a time)
                entry[kind] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            frames[fid].append(entry)
    meta = {"year": int(year), "fields": [
        {"id": int(fid), "file": files.get(fid, f"farm_{fid}.json"), "name": names.get(fid, f"Field {fid}"),
         "design": designs.get(fid, ""), "frames": frames[fid]} for fid in fields_lonlat]}
    with open(os.path.join(out_dir, "timeline.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    for f in meta["fields"]:
        print(f"{f['name']}: {len(f['frames'])} clear pictures in {year}")
    return meta

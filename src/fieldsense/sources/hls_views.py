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


def add_plot_views(found, plots_lonlat, out_dir, designs=None, scale=24, key="plots", prefix="plot", names=None,
                   context_m=None, size=240):
    """For the dates in `found` (from find_clear_views), save each plot's true-colour and
    greenness picture and add a table (rows = fields, columns = dates) to space.json under `key`
    ("plots" for the trial plots, "farms" for nearby farm fields)."""
    from PIL import Image
    designs = designs or {}
    rows = {pid: [] for pid in sorted(plots_lonlat)}
    for i, f in enumerate(found, start=1):
        views = (read_field_context(f["links"], plots_lonlat, None if context_m == "auto" else context_m / 2) if context_m
                 else read_plot_views(f["links"], plots_lonlat))
        for pid in rows:
            v = views[pid]
            tile = {}
            for kind, make in (("true", true_colour), ("green", greenness)):
                if context_m:          # the field in its surroundings, smoothly enlarged
                    tile[kind] = f"{prefix}{pid}_{i}_{kind}.jpg"
                    render_context(make(v), v["poly_px"], size=size).save(os.path.join(out_dir, tile[kind]), quality=85)
                    continue
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
        "note": ("Each field is shown in a 1 km square of its surroundings (dimmed)." if context_m
                 else "Only each field's own 30 m pixels are shown; nothing outside the field."),
        "view": "context" if context_m else "field",
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
                       max_bad=0.1, scale=6, context_m=None, max_bad_context=0.35, size=360):
    """Every clear picture of each field through one year, for the page's "Watch a year" animation.

    granules: from `search_granules` (one year). A picture is kept when at most `max_bad`
    of the field's pixels are cloudy or missing. Saves timeline.json, with the pictures packed inside it.

    context_m=None: only the field's own pixels (everything else transparent).
    context_m=1000: a 1 km square around the field, smoothly enlarged to `size` pixels, with the
    field bright and its surroundings dimmed (and at most `max_bad_context` cloud in the square).
    """
    import base64
    import io
    from PIL import Image
    designs, names, files = designs or {}, names or {}, files or {}
    frames = {fid: [] for fid in fields_lonlat}
    for n, g in enumerate(granules, start=1):
        try:
            views = (read_field_context(g["links"], fields_lonlat, None if context_m == "auto" else context_m / 2) if context_m
                     else read_plot_views(g["links"], fields_lonlat))
        except Exception as err:
            print(f"  skipped {g['date']}: {err}")
            continue
        if n % 10 == 0:
            print(f"  read {n} of {len(granules)} passes")
        for fid, v in views.items():
            if v["bad_fraction"] > max_bad or (frames[fid] and frames[fid][-1]["date"] == g["date"]):
                continue
            if context_m and v["bad_fraction_all"] > max_bad_context:
                continue
            entry = {"date": g["date"], "clear": round(1 - v["bad_fraction"], 3)}
            for kind, make in (("true", true_colour), ("green", greenness)):
                buf = io.BytesIO()
                if context_m:
                    render_context(make(v), v["poly_px"], size=size).save(buf, format="JPEG", quality=82, optimize=True)
                    mime = "image/jpeg"
                else:
                    img = Image.fromarray(_with_alpha(make(v), v["inside"]), "RGBA")
                    img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
                    img.save(buf, format="PNG", optimize=True)
                    mime = "image/png"
                # packed inside timeline.json: one file instead of hundreds (GitHub's web upload takes 100 at a time)
                entry[kind] = f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()
            frames[fid].append(entry)
    meta = {"year": int(year), "view": "context" if context_m else "field", "fields": [
        {"id": int(fid), "file": files.get(fid, f"farm_{fid}.json"), "name": names.get(fid, f"Field {fid}"),
         "design": designs.get(fid, ""), "frames": frames[fid]} for fid in fields_lonlat]}
    with open(os.path.join(out_dir, "timeline.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    for f in meta["fields"]:
        print(f"{f['name']}: {len(f['frames'])} clear pictures in {year}")
    return meta


# ------------------------------------------------------------------ a field in its surroundings
def read_field_context(links, fields_lonlat, half_size_m=500):
    """A square around each field's centre: {field_id: view}. half_size_m=None sizes each square
    to its field (at least 1 km wide, with a margin around large fields). view["poly_px"] is the field's
    outline in pixel coordinates (to draw a smooth highlight); "bad_fraction" counts only the
    field's own pixels, "bad_fraction_all" the whole square."""
    out = {}
    with rasterio.Env(**hls.GDAL_OPTS):
        with hls._open(links["red"]) as src:
            geoms = hls.plots_in_crs(fields_lonlat, src.crs, inner_buffer_m=0)
            wins = {}
            full = Window(0, 0, src.width, src.height)
            for fid, g in geoms.items():
                c = g.centroid
                minx, miny, maxx, maxy = g.bounds
                h = half_size_m or max(500, 0.65 * max(maxx - minx, maxy - miny))   # None: fit big fields
                w = from_bounds(c.x - h, c.y - h, c.x + h, c.y + h, transform=src.transform)
                win = Window(int(round(w.col_off)), int(round(w.row_off)), int(round(w.width)), int(round(w.height)))
                # read only the part inside the image tile (boundless reads fail on remote files) and pad the rest
                inner = win.intersection(full)
                wins[fid] = (win, src.window_transform(win), inner)
            bands = {fid: {"red": _padded(src, win, inner, NODATA)} for fid, (win, _, inner) in wins.items()}
        for key in ("green", "blue", "nir", "fmask"):
            with hls._open(links[key]) as src:
                for fid, (win, _, inner) in wins.items():
                    bands[fid][key] = _padded(src, win, inner, 255 if key == "fmask" else NODATA)
    for fid, b in bands.items():
        win, tr, _ = wins[fid]
        inside = geometry_mask([mapping(geoms[fid])], out_shape=b["red"].shape, transform=tr, invert=True)
        fmask = b.pop("fmask")
        nodata = np.zeros(fmask.shape, bool)
        for v in b.values():
            nodata |= v <= NODATA
        bad = nodata | (fmask == 255) | ((fmask & hls.BAD_FMASK_BITS) != 0)
        refl = {k: np.where(v <= NODATA, np.nan, v * SCALE).astype("float32") for k, v in b.items()}
        inv = ~tr
        poly_px = [tuple(inv @ (x, y)) if hasattr(inv, "__matmul__") else inv * (x, y) for x, y in geoms[fid].exterior.coords]
        out[fid] = {**refl, "bad": bad, "inside": inside, "poly_px": poly_px,
                    "bad_fraction": float(bad[inside].mean()) if inside.any() else 1.0,
                    "bad_fraction_all": float(bad.mean())}
    return out


def _padded(src, win, inner, fill):
    """Read `inner` (the part of `win` inside the tile) and place it in a `win`-sized array."""
    out = np.full((int(win.height), int(win.width)), fill, dtype=src.dtypes[0])
    if inner.width > 0 and inner.height > 0:
        data = src.read(1, window=inner)
        r0, c0 = int(inner.row_off - win.row_off), int(inner.col_off - win.col_off)
        out[r0:r0 + data.shape[0], c0:c0 + data.shape[1]] = data
    return out


def neat_outline(poly_px, rect_fill=0.72, grow_px=0.5):
    """A cleaner field outline from a pixel-staircase one (pixel coordinates).

    Crop-map fields are traced along 30 m pixels, so slanted edges look like stairs. A field
    whose smallest rotated rectangle stays within about one pixel of it everywhere (the stairs
    themselves; not a missing corner) is drawn as a rectangle with that orientation and the field's own area; any other
    shape is smoothed (stairs rounded off). `grow_px` makes up for the ring of edge pixels that
    was trimmed when the field was found.
    """
    from shapely.affinity import scale
    from shapely.geometry import Polygon
    p = Polygon(poly_px).buffer(0)
    if p.is_empty or p.area <= 0:
        return list(poly_px)
    if p.geom_type != "Polygon":
        p = max(p.geoms, key=lambda g: g.area)
    target = p.buffer(grow_px, join_style=2).area
    r = p.minimum_rotated_rectangle
    # a rectangle only if it stays within ~1 pixel of the field everywhere (stairs yes, a missing corner no)
    outside = r.difference(p.buffer(1.0, join_style=2)).area / r.area if r.area > 0 else 1.0
    if outside < 0.03 and p.area / r.area >= rect_fill:
        k = (target / r.area) ** 0.5
        q = scale(r, k, k, origin=r.centroid)
    else:
        q = p.buffer(grow_px, join_style=2).simplify(0.9)                 # straighten stairs, keep corners
    if q.geom_type != "Polygon":
        q = max(q.geoms, key=lambda g: g.area)
    return [tuple(c) for c in q.exterior.coords]


def render_context(rgb, poly_px, size=360, dim=0.5, edge=(255, 255, 255), neat=True):
    """Smoothly enlarge a small satellite square and highlight one field: the field keeps its
    colours, the surroundings are dimmed and a little greyer, with a soft white edge."""
    from PIL import Image, ImageDraw, ImageFilter
    if neat:
        poly_px = neat_outline(poly_px)
    h, w = rgb.shape[:2]
    img = Image.fromarray(rgb).resize((size, size), Image.BICUBIC)
    ss = 4                                                   # draw the outline 4x larger, then shrink: smooth edges
    sx, sy = size * ss / w, size * ss / h
    pts = [(x * sx, y * sy) for x, y in poly_px]
    mask = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    mask = mask.resize((size, size), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6))
    line = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(line).line(pts + pts[:1], fill=230, width=2 * ss, joint="curve")
    line = line.resize((size, size), Image.LANCZOS)
    arr = np.asarray(img).astype("float32")
    grey = arr.mean(axis=2, keepdims=True)
    outside = (0.6 * arr + 0.4 * grey) * dim
    m = np.asarray(mask, dtype="float32")[..., None] / 255
    out = arr * m + outside * (1 - m)
    a = np.asarray(line, dtype="float32")[..., None] / 255 * 0.85
    out = out * (1 - a) + np.array(edge, "float32") * a
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def pick_showcase(profiles, designs, areas=None, min_year=2016, min_observed=150):
    """Choose the simple field, diverse field and year where the satellite measured the biggest
    difference in soil cover: fewer bare days and more off-season green on the diverse field.

    profiles: {field_id: profile dict}; designs: {field_id: "simple" | "diverse"};
    areas: {field_id: hectares} (breaks ties toward bigger fields, which look better).
    Returns {"simple", "diverse", "year", "bare_days", "offseason_green"} or None.
    """
    areas = areas or {}
    per = {fid: {r["year"]: r for r in p.get("cover", {}).get("per_year", [])} for fid, p in profiles.items()}
    best = None
    for d in (f for f in profiles if designs.get(f) == "diverse"):
        for s in (f for f in profiles if designs.get(f) == "simple"):
            for y in sorted(set(per[d]) & set(per[s])):
                rd, rs = per[d][y], per[s][y]
                if y < min_year or min(rd.get("observed_days") or 0, rs.get("observed_days") or 0) < min_observed:
                    continue
                share_d, share_s = rd.get("green_share_off_season") or 0, rs.get("green_share_off_season") or 0
                score = (rs["bare_days"] - rd["bare_days"]) + 100 * (share_d - share_s)
                key = (round(score, 3), areas.get(s, 0) + areas.get(d, 0), y)
                if best is None or key > best[0]:
                    best = (key, {"simple": s, "diverse": d, "year": int(y),
                                  "bare_days": {"simple": rs["bare_days"], "diverse": rd["bare_days"]},
                                  "offseason_green": {"simple": round(share_s, 2), "diverse": round(share_d, 2)}})
    return best[1] if best else None

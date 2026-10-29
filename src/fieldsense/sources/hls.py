"""NASA HLS (Harmonized Landsat Sentinel-2): 30 m surface reflectance every 2-3 days.

From Lesson 4. Images are Cloud-Optimized GeoTIFFs (COGs) in NASA's cloud, so we read
only the few kilobytes covering our fields, not the whole ~110 km tile.

Two lessons built in:
  - Mixed pixels: plots are shrunk inward by one pixel (30 m) so every pixel used is pure.
  - Login: GDAL (inside rasterio) has its own login; set OPENER to earthaccess's
    authenticated session so NASA sends images instead of its login page.
"""
import os
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window, from_bounds
from rasterio.features import geometry_mask
import shapely
from shapely.geometry import Polygon, mapping
from pyproj import Transformer

# GDAL settings recommended by NASA LP DAAC for reading HLS over HTTPS with an Earthdata login (~/.netrc)
GDAL_OPTS = dict(
    GDAL_HTTP_COOKIEFILE=os.path.expanduser("~/cookies.txt"),
    GDAL_HTTP_COOKIEJAR=os.path.expanduser("~/cookies.txt"),
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS="TIF",
    GDAL_HTTP_NETRC="YES",
    GDAL_HTTP_MAX_RETRY="5",
    GDAL_HTTP_RETRY_DELAY="1",
)
NIR_BAND = {"L30": "B05", "S30": "B8A"}      # near-infrared band name differs between the two sensors
RED_BAND = "B04"
OPENER = None   # set to an authenticated file opener (earthaccess); None = let GDAL log in via ~/.netrc

def _open(path):
    return rasterio.open(path, opener=OPENER) if OPENER else rasterio.open(path)
BAD_FMASK_BITS = 0b00011110                    # bits 1-4: cloud, adjacent cloud/shadow, shadow, snow/ice

def granule_info(native_id):
    """'HLS.L30.T17TNJ.2023185T160919.v2.0' -> sensor 'L30', tile 'T17TNJ', date 2023-07-04."""
    parts = native_id.split(".")
    return {"granule": native_id, "sensor": parts[1], "tile": parts[2],
            "date": pd.to_datetime(parts[3][:7], format="%Y%j")}

def band_links(urls, sensor):
    """Pick the red, near-infrared and cloud-mask file links out of all of a granule's links."""
    wanted = {"red": RED_BAND, "nir": NIR_BAND[sensor], "fmask": "Fmask"}
    out = {}
    for key, band in wanted.items():
        match = [u for u in urls if u.endswith(f".{band}.tif")]
        if match:
            out[key] = match[0]
    return out if len(out) == 3 else None

def plots_in_crs(plots_lonlat, crs, inner_buffer_m=30):
    """Project plot polygons from lon/lat into the image's coordinate system and shrink them inward."""
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    out = {}
    for pid, coords in plots_lonlat.items():
        xs, ys = tr.transform([c[0] for c in coords], [c[1] for c in coords])
        out[pid] = Polygon(zip(xs, ys)).buffer(-inner_buffer_m)
    return out

def read_plot_ndvi(links, plots_lonlat, inner_buffer_m=30, min_valid_fraction=0.5):
    """Mean NDVI of the pure, cloud-free pixels in each plot for one HLS granule.
    Returns {plot_id: (ndvi or NaN, n_valid_pixels, n_plot_pixels)}."""
    with rasterio.Env(**GDAL_OPTS):
        with _open(links["red"]) as src:
            geoms = plots_in_crs(plots_lonlat, src.crs, inner_buffer_m)
            minx, miny, maxx, maxy = shapely.union_all(list(geoms.values())).bounds
            w = from_bounds(minx - 60, miny - 60, maxx + 60, maxy + 60, transform=src.transform)
            win = Window(int(np.floor(w.col_off)), int(np.floor(w.row_off)),
                         int(np.ceil(w.width)) + 1, int(np.ceil(w.height)) + 1)
            red = src.read(1, window=win).astype("float32")
            wtr = src.window_transform(win)
        with _open(links["nir"]) as src:
            nir = src.read(1, window=win).astype("float32")
        with _open(links["fmask"]) as src:
            fmask = src.read(1, window=win)
    valid = ((fmask & BAD_FMASK_BITS) == 0) & (red > 0) & (nir > 0) & (fmask != 255)
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (nir - red) / (nir + red)
    result = {}
    for pid, geom in geoms.items():
        inside = geometry_mask([mapping(geom)], out_shape=red.shape, transform=wtr, invert=True)
        ok = inside & valid
        n_in, n_ok = int(inside.sum()), int(ok.sum())
        mean = float(np.nanmean(ndvi[ok])) if n_in and n_ok >= min_valid_fraction * n_in else float("nan")
        result[pid] = (mean, n_ok, n_in)
    return result


def use_earthaccess_login(block_size=256 * 1024):
    """Route every image read through earthaccess's working Earthdata login (the Lesson 4 fix).

    Call once after `earthaccess.login(...)`. block_size: download in 256 KB pieces, so only
    the parts of each image we need are fetched.
    """
    global OPENER
    import earthaccess
    fs = earthaccess.get_fsspec_https_session()
    OPENER = lambda path, mode="rb": fs.open(path, mode, block_size=block_size, cache_type="blockcache")
    return OPENER

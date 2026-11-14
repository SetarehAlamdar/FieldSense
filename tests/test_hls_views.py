"""Checks for fieldsense.sources.hls_views, on small synthetic satellite files (no download)."""
import json

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin

from fieldsense.sources import hls_views

LON, LAT = -80.41, 43.64
X0, Y0 = 547000, 4834000          # UTM zone 17N, around Elora


def _write_granule(tmp_path, red, nir, fmask, n=200):
    """Write fake B02/B03/B04/B05/Fmask files: n x n pixels of 30 m, as HLS L30 stores them."""
    tr = from_origin(X0 - n * 15, Y0 + n * 15, 30, 30)
    urls = []
    for band, value in (("B02", 300), ("B03", 500), ("B04", red), ("B05", nir), ("Fmask", fmask)):
        path = tmp_path / f"HLS.L30.T17TNJ.2023290T160000.v2.0.{band}.tif"
        dtype = "uint8" if band == "Fmask" else "int16"
        arr = np.asarray(value, dtype=dtype)
        arr = np.full((n, n), arr, dtype=dtype) if arr.ndim == 0 else arr
        with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype=dtype,
                           crs="EPSG:32617", transform=tr) as dst:
            dst.write(arr, 1)
        urls.append(str(path))
    return hls_views.view_links(urls, "L30")


def test_read_view_returns_a_square_and_counts_clouds(tmp_path):
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True).transform(X0, Y0)
    fmask = np.zeros((200, 200), "uint8")
    fmask[:100, :] = 0b00000010                 # top half cloudy
    links = _write_granule(tmp_path, red=400, nir=3000, fmask=fmask)
    v = hls_views.read_view(links, lon, lat, half_size_m=1500)
    assert v["red"].shape == (100, 100)         # 3 km / 30 m
    assert 0.4 < v["bad_fraction"] < 0.6
    assert v["nir"][-1, -1] == pytest.approx(0.3)


def test_pictures_are_rgb_and_vegetation_is_green(tmp_path):
    from pyproj import Transformer
    lon, lat = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True).transform(X0, Y0)
    links = _write_granule(tmp_path, red=400, nir=4000, fmask=0)      # dense vegetation, no clouds
    v = hls_views.read_view(links, lon, lat, half_size_m=600)
    g = hls_views.greenness(v)
    t = hls_views.true_colour(v)
    assert g.shape[2] == 3 and t.dtype == np.uint8
    assert g[0, 0, 1] > g[0, 0, 0]              # NDVI ~0.82 -> more green than red


def test_save_views_writes_images_and_index(tmp_path):
    v = {"red": np.full((5, 5), 0.05, "float32"), "green": np.full((5, 5), 0.06, "float32"),
         "blue": np.full((5, 5), 0.04, "float32"), "nir": np.full((5, 5), 0.3, "float32"),
         "bad": np.zeros((5, 5), bool), "bad_fraction": 0.0}
    meta = hls_views.save_views([{"label": "Late October", "date": "2023-10-20", "sensor": "S30", "view": v}], tmp_path)
    assert (tmp_path / "space_1_true.png").exists() and (tmp_path / "space_1_green.png").exists()
    assert json.loads((tmp_path / "space.json").read_text())["views"][0]["label"] == "Late October"
    assert meta["views"][0]["clear_share"] == 1.0



def test_plot_views_show_only_pixels_inside_each_plot(tmp_path):
    from pyproj import Transformer
    to_ll = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True).transform
    square = lambda x, y, s: [to_ll(x, y), to_ll(x + s, y), to_ll(x + s, y + s), to_ll(x, y + s), to_ll(x, y)]
    plots = {1: square(X0 - 300, Y0 - 300, 200), 2: square(X0 + 100, Y0 + 100, 200)}
    links = _write_granule(tmp_path, red=400, nir=3000, fmask=0)
    views = hls_views.read_plot_views(links, plots)
    for v in views.values():
        assert 30 < v["inside"].sum() < 60                # 200 m x 200 m = about 44 pixels of 30 m
        assert not v["inside"].all()                       # the frame around the plot is masked out
    found = [{"label": "Late October", "date": "2023-10-20", "links": links}]
    meta = hls_views.add_plot_views(found, plots, tmp_path, designs={1: "simple", 2: "diverse"})
    assert [r["design"] for r in meta["plots"]["rows"]] == ["simple", "diverse"]
    from PIL import Image
    img = Image.open(tmp_path / meta["plots"]["rows"][0]["tiles"][0]["green"])
    assert img.mode == "RGBA" and img.getpixel((0, 0))[3] == 0     # corner outside the plot is transparent

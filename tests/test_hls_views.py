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



def test_field_timeline_keeps_only_clear_pictures(tmp_path):
    from pyproj import Transformer
    to_ll = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True).transform
    square = lambda x, y, s: [to_ll(x, y), to_ll(x + s, y), to_ll(x + s, y + s), to_ll(x, y + s), to_ll(x, y)]
    fields = {1: square(X0 - 300, Y0 - 300, 300)}
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    clear = _write_granule(tmp_path / "a", red=400, nir=3000, fmask=0)
    cloudy = _write_granule(tmp_path / "b", red=400, nir=3000, fmask=0b00000010)
    grans = [{"date": "2023-05-10", "links": clear}, {"date": "2023-05-20", "links": cloudy},
             {"date": "2023-06-01", "links": clear}]
    meta = hls_views.add_field_timeline(grans, fields, tmp_path, 2023, designs={1: "simple"})
    frames = meta["fields"][0]["frames"]
    assert [f["date"] for f in frames] == ["2023-05-10", "2023-06-01"]      # the cloudy date is dropped
    assert frames[0]["green"].startswith("data:image/png;base64,")         # pictures packed in the JSON
    assert json.loads((tmp_path / "timeline.json").read_text())["year"] == 2023



def test_context_view_shows_the_field_in_its_surroundings(tmp_path):
    from pyproj import Transformer
    to_ll = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=True).transform
    square = lambda x, y, s: [to_ll(x, y), to_ll(x + s, y), to_ll(x + s, y + s), to_ll(x, y + s), to_ll(x, y)]
    fields = {1: square(X0 - 150, Y0 - 150, 300)}
    links = _write_granule(tmp_path, red=400, nir=3000, fmask=0)
    v = hls_views.read_field_context(links, fields, half_size_m=500)[1]
    assert v["red"].shape[0] in (33, 34) and 50 < v["inside"].sum() < 150     # 1 km square, 300 m field
    img = hls_views.render_context(hls_views.greenness(v), v["poly_px"], size=200)
    assert img.size == (200, 200)
    px = np.asarray(img).astype(int)
    assert px[100, 100].sum() > px[5, 5].sum()                                 # field bright, surroundings dimmed
    grans = [{"date": "2023-05-10", "links": links}]
    meta = hls_views.add_field_timeline(grans, fields, tmp_path, 2023, context_m=1000, size=200)
    assert meta["view"] == "context" and meta["fields"][0]["frames"][0]["green"].startswith("data:image/jpeg")


def test_showcase_picks_the_biggest_measured_difference():
    def prof(rows):
        return {"cover": {"per_year": [dict(year=y, observed_days=220, bare_days=b, green_share_off_season=g) for y, b, g in rows]}}
    profiles = {1: prof([(2020, 140, 0.0), (2023, 120, 0.05)]),
                2: prof([(2020, 60, 0.6), (2023, 100, 0.1)]),
                3: prof([(2020, 90, 0.3), (2023, 20, 0.7)])}
    pick = hls_views.pick_showcase(profiles, {1: "simple", 2: "diverse", 3: "diverse"})
    assert (pick["simple"], pick["diverse"], pick["year"]) == (1, 3, 2023)     # 100 fewer bare days + 65 points

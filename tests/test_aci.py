"""Checks for fieldsense.sources.aci on a synthetic crop map (no download)."""
import numpy as np
import pytest

pytest.importorskip("scipy")
pytest.importorskip("rasterio")
from fieldsense.sources import aci

C, S, W = aci.CORN, aci.SOY, aci.WINTER_WHEAT


def test_rotation_groups():
    assert aci.rotation_group([C, S, S, C, S, S]) == "simple"
    assert aci.rotation_group([S, W, C, S, W, C]) == "diverse"
    assert aci.rotation_group([C, C, C]) is None                  # monoculture: neither
    assert aci.rotation_group([S, W, C, 122]) is None              # pasture in the sequence: neither


def test_find_fields_on_a_synthetic_map():
    years = list(range(2015, 2026))
    h = w = 120                                                    # 3.6 km square
    simple = [C, S, S] * 4
    diverse = [S, W, C] * 4
    stack = np.full((len(years), h, w), 122, dtype=np.uint8)      # pasture background
    for i in range(len(years)):
        stack[i, 10:40, 10:40] = simple[i]                         # 30 x 30 px = 81 ha
        stack[i, 60:90, 60:100] = diverse[i]                       # 30 x 40 px = 108 ha
    stack[3, 20, 20] = W                                           # one misclassified pixel: smoothed away
    epsg, box = aci.box_around(-80.41, 43.64, 1800)
    fields = aci.find_fields(stack, years, epsg, box, min_ha=20)
    groups = sorted(f["group"] for f in fields)
    assert groups == ["diverse", "simple"]
    d = [f for f in fields if f["group"] == "diverse"][0]
    assert d["crops"][2016] == "winter wheat" and d["area_ha"] > 80
    assert len(d["lonlat"]) >= 4 and -81 < d["lonlat"][0][0] < -80


def test_exclude_radius_skips_fields_near_a_point():
    years = list(range(2015, 2026))
    stack = np.full((len(years), 120, 120), 122, dtype=np.uint8)
    for i in range(len(years)):
        stack[i, 45:75, 45:75] = [C, S, S][i % 3]                  # field right at the centre
    epsg, box = aci.box_around(-80.41, 43.64, 1800)
    assert aci.find_fields(stack, years, epsg, box, exclude=(-80.41, 43.64, 1000)) == []

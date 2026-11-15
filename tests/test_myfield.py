"""Checks for fieldsense.myfield on a fake crop map and fake history (no internet)."""
import numpy as np

from fieldsense import myfield as mf
from fieldsense.sources import aci


def test_field_at_point_finds_the_field_under_the_point(tmp_path, monkeypatch):
    lon, lat = -80.41, 43.64
    epsg, box = aci.box_around(lon, lat, 1500)
    n = int((box[2] - box[0]) / 30)
    def fake(year, epsg_, box_, cache_dir):
        a = np.full((n, n), 147 if year % 2 else 158, dtype="uint8")        # corn / soybean all around
        a[:, : n // 2 - 3] = 153                                             # canola field on the west side
        return a
    monkeypatch.setattr(aci, "get_aci", fake)
    f = mf.field_at_point(lon, lat, str(tmp_path))
    assert f is not None and f["group"] == "simple"
    assert set(f["crops"].values()) == {"corn", "soybean"} and 300 < f["area_ha"] < 500


def test_rotation_advice_for_ontario_and_not_for_prairie():
    odds = {"risks": {"heavy_rain_on_bare_soil": {"share": 0.3}, "pollination_heat": {"share": 0.2},
                      "late_spring_frost": {"share": 0.1}, "early_fall_frost": {"share": 0.1},
                      "summer_dry_spell": {"share": 0.05}, "short_fall_after_soybean": {"share": 0.02}}}
    hist = [{"year": y, "satellite_says": "corn or soybean"} for y in range(2021, 2026)]
    cover = {"green_share_off_season": 0.02, "spring_bare_share": 0.98}
    on = mf.rotation_advice(hist, odds, cover, {y: (147 if y % 2 else 158) for y in range(2019, 2026)})
    assert on["available"] and on["current"] == "CSS" and abs(sum(on["robustness"].values()) - 1) < 1e-6
    assert "measured by satellite" in on["why"]["CSS"]["soil_cover"]["text"]
    prairie = mf.rotation_advice(hist, odds, cover, {y: (153 if y % 2 else 146) for y in range(2019, 2026)})
    assert not prairie["available"] and "canola" in prairie["reason"]



def test_a_point_in_town_is_not_called_a_field(tmp_path, monkeypatch):
    lon, lat = -107.99, 51.55
    epsg, box = aci.box_around(lon, lat, 1500)
    n = int((box[2] - box[0]) / 30)
    monkeypatch.setattr(aci, "get_aci", lambda y, e, b, cache_dir: np.full((n, n), 34, dtype="uint8"))
    f = mf.field_at_point(lon, lat, str(tmp_path))
    assert f["farmland"] is False and f["land"] == "urban / developed"

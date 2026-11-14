"""Checks for fieldsense.export: the privacy gate before anything is published."""
import json

import numpy as np
import pandas as pd
import pytest

from fieldsense import export


def _profile():
    return {"schema": "0.3", "field": {"id": "p1", "name": "Plot 1", "lat": 43.640614, "lon": -80.414289,
                                       "area_ha": 4.76, "location_source": "survey map"},
            "history": [], "cover": {}, "gaps": []}


def test_public_profile_rounds_coordinates_and_drops_private_fields():
    pub = export.public_profile(_profile())
    assert pub["field"]["lat"] == 43.64 and pub["field"]["lon"] == -80.41
    assert "area_ha" not in pub["field"] and "location_source" not in pub["field"]
    assert export.check_public(pub) == []


def test_original_profile_is_not_changed():
    p = _profile()
    export.public_profile(p)
    assert p["field"]["area_ha"] == 4.76                      # we copy, never edit the original


def test_check_public_catches_private_things():
    assert export.check_public(_profile())                   # unrounded + area -> problems
    assert export.check_public({"note": "from elora_ground_truth_PRIVATE.json"})


def test_barcode_payload_is_compact_and_marks_unseen_days_as_null():
    # constant greenness 0.5, so the smoothed value is known exactly
    dates = pd.to_datetime(["2020-05-01", "2020-05-11", "2020-08-01"])
    payload = export.barcode_payload(pd.DataFrame({"date": dates, "ndvi": [0.5, 0.5, 0.5]}))
    row = payload["values"][0]
    assert payload["years"] == [2020] and len(row) == 365
    assert row[121] == 50 and row[126] == 50                  # 1 May and 6 May (short gap: filled)
    assert row[160] is None                                   # mid-June: inside an 82-day gap
    assert row[0] is None                                     # January: before the first look


def test_export_demo_writes_safe_files(tmp_path):
    prof_dir, out_dir = tmp_path / "profiles", tmp_path / "site"
    prof_dir.mkdir()
    (prof_dir / "plot_1.json").write_text(json.dumps(_profile()))
    (prof_dir / "evidence.json").write_text(json.dumps({"evidence": [{"id": "x", "label": "measured"}]}))
    days = pd.date_range("2020-04-01", "2020-10-31", freq="5D")
    pd.DataFrame({"date": days, "plot": 1, "ndvi": np.linspace(0.2, 0.8, len(days))}).to_csv(tmp_path / "hls.csv", index=False)
    written = export.export_demo(prof_dir, tmp_path / "hls.csv", out_dir)
    assert {p.split("/")[-1] for p in map(str, written)} == {"plot_1.json", "evidence.json", "index.json"}
    pub = json.loads((out_dir / "plot_1.json").read_text())
    assert export.check_public(pub) == [] and pub["barcode"]["years"] == [2020]
    assert json.loads((out_dir / "index.json").read_text())["fields"][0]["file"] == "plot_1.json"


def test_export_demo_copies_figures_when_available(tmp_path):
    prof_dir, demo_dir, out_dir = tmp_path / "profiles", tmp_path / "demo", tmp_path / "site"
    prof_dir.mkdir(); demo_dir.mkdir()
    (prof_dir / "plot_1.json").write_text(json.dumps(_profile()))
    (demo_dir / "living_cover_elora.png").write_bytes(b"png")       # one of the three figures exists
    days = pd.date_range("2020-04-01", "2020-10-31", freq="5D")
    pd.DataFrame({"date": days, "plot": 1, "ndvi": 0.5}).to_csv(tmp_path / "hls.csv", index=False)
    export.export_demo(prof_dir, tmp_path / "hls.csv", out_dir, demo_dir=demo_dir)
    figs = json.loads((out_dir / "index.json").read_text())["figures"]
    assert [f["file"] for f in figs] == ["fig_living_cover.png"]
    assert (out_dir / "fig_living_cover.png").exists()


def test_current_rotation_uses_measured_cover_and_robustness_is_recomputed():
    from fieldsense import rotation as rt
    from fieldsense.climate import RISKS
    odds = {"risks": {k: {"share": 0.2} for k in RISKS}}
    table = rt.compare(rt.CANDIDATES, odds).round(4).reset_index()
    pub = {"climate_odds": odds,
           "rotation_options": {"current": "CSS", "candidates": json.loads(table.to_json(orient="records")),
                                "calendar_model_evidence": "modelled", "robustness_best_share": {}}}
    before = [c for c in pub["rotation_options"]["candidates"] if c["key"] == "CSS"][0]["climate_risk_total"]
    days = pd.date_range("2018-03-01", "2019-11-30", freq="3D")
    m = __import__("fieldsense").barcode_matrix(__import__("fieldsense").daily_ndvi(
        pd.DataFrame({"date": days, "ndvi": 0.8})))             # green all season, every year
    export.use_measured_cover(pub, m)
    css = [c for c in pub["rotation_options"]["candidates"] if c["key"] == "CSS"][0]
    assert css["cover_evidence"] == "measured" and css["spring_bare_share"] == 0.0
    assert css["risk_heavy_rain_on_bare_soil"] == 0.0 and css["climate_risk_total"] < before   # no bare soil, no rain-on-bare risk
    assert [c for c in pub["rotation_options"]["candidates"] if c["key"] == "SWC"][0]["cover_evidence"] == "modelled"
    assert abs(sum(pub["rotation_options"]["robustness_best_share"].values()) - 1) < 0.01


def test_highlights_compare_conventional_and_diverse():
    def pub(cur, bare, green, nxt):
        return {"rotation_options": {"current": cur, "next_crop_2026": nxt,
                                     "measured_cover": {"spring_bare_share": bare, "green_share_off_season": green}},
                "climate_odds": {"risks": {"heavy_rain_on_bare_soil": {"share": 0.26, "past_years": "7 of 30"}}}}
    h = export.highlights([pub("CSS", 1.0, 0.03, "corn or soybean (ask)"), pub("SWC+covers", 0.64, 0.39, "winter wheat")])
    assert [r["value"] for r in h[0]["rows"]] == [100, 64]         # bare in spring: conventional, diverse
    assert [r["value"] for r in h[1]["rows"]] == [3, 39]           # living cover outside summer
    assert h[0]["rows"][0]["label"].startswith("Conventional")
    assert [x.get("big") for x in h[2:]] == ["26 in 100", "Winter wheat"]

"""Checks for fieldsense.rotation.

Two kinds of test here:
- EXAMPLE tests: a known input with a known answer (corn-soybean repeats every 2 years).
- PROPERTY tests: a rule that must hold for ANY input ("adding a cover crop never reduces
  living cover"). They don't need us to know the right number, so they're less exposed to
  our own possibly wrong assumptions.
"""
import numpy as np
import pandas as pd
import pytest

from fieldsense import rotation as rt
from fieldsense.climate import RISKS

CAND = {r.key: r for r in rt.CANDIDATES}
ODDS = {"risks": {k: {"share": 0.2} for k in RISKS}}      # every risk 20 in 100


def test_crop_table_loads_from_the_package():
    t = rt.load_crop_table()
    assert {"corn", "soybean", "winter_wheat"} <= set(t["crops"])


@pytest.mark.parametrize("key,gap", [("CS", 2), ("SWC", 3), ("SWC+clover", 3)])
def test_years_between_same_crop(key, gap):
    assert rt.agronomy_metrics(CAND[key])["min_years_between_same_crop"] == gap


def test_wheat_is_green_the_fall_before_its_year():
    g = rt.green_calendar(CAND["SWC"])          # soybean, wheat, corn
    assert g[0, 310 - 1]                        # soybean year, 6 Nov: the wheat sown after soybean is up
    assert not g[2, 310 - 1]                    # corn year, 6 Nov: bare


@pytest.mark.parametrize("with_cover,without", [("CS+rye", "CS"), ("SWC+clover", "SWC")])
def test_property_adding_a_cover_never_reduces_cover(with_cover, without):
    a, b = rt.cover_metrics(CAND[with_cover]), rt.cover_metrics(CAND[without])
    assert a["green_share_off_season"] >= b["green_share_off_season"]
    assert a["spring_bare_share"] <= b["spring_bare_share"]


def test_property_shares_are_between_0_and_1():
    for r in rt.CANDIDATES:
        assert all(0 <= v <= 1 for v in rt.cover_metrics(r).values())


def test_no_corn_means_no_pollination_heat_exposure():
    soy_only = rt.Rotation("S", "Soybean", ["soybean"])
    assert rt.climate_exposure(soy_only, ODDS)["pollination_heat"] == 0


def test_rye_after_soybean_is_exposed_to_a_short_fall():
    assert rt.climate_exposure(CAND["CS+rye"], ODDS)["short_fall_after_soybean"] > 0
    assert rt.climate_exposure(CAND["CS"], ODDS)["short_fall_after_soybean"] == 0


def test_a_rotation_better_on_every_criterion_always_wins():
    t = pd.DataFrame({"a": [1.0, 0.0, 1.0], "b": [0.0, 1.0, 0.0]}, index=["best", "worst", "tie"])
    t.loc["best"] = [1.0, 0.0]
    t.loc["tie"] = [0.5, 0.5]
    share = rt.rank_robustness(t, criteria={"a": +1, "b": -1}, n=500)
    assert share["best"] == 1.0


def test_weighted_ranking_follows_the_weights():
    t = rt.compare(rt.CANDIDATES, ODDS)
    only_cover = rt.weighted_ranking(t, {"green_share_off_season": 1})
    assert only_cover.index[0] == "SWC+clover"


def test_detect_current_and_next_crop():
    hist = [{"year": 2020, "satellite_says": "winter wheat + green after harvest (cover crop?)"},
            {"year": 2021, "satellite_says": "corn or soybean + green in spring (overwintered cover crop?)"},
            {"year": 2022, "satellite_says": "corn or soybean"},
            {"year": 2023, "satellite_says": "winter wheat + green after harvest (cover crop?)"},
            {"year": 2024, "satellite_says": "corn or soybean + green in spring (overwintered cover crop?)"},
            {"year": 2025, "satellite_says": "corn or soybean"}]
    assert rt.detect_current(hist) == "SWC+clover"
    assert rt.next_crop("SWC+clover", hist, 2026) == "winter wheat"
    assert rt.next_crop("SWC+clover", hist, 2027) == "corn"
    assert rt.detect_current([{"year": 2025, "satellite_says": "corn or soybean"}]) == "CS"


def test_explanation_has_five_parts_each_with_evidence():
    t = rt.compare(rt.CANDIDATES, ODDS)
    ex = rt.explain(t.loc["CS"], current_key="CS", evidence={})
    assert list(ex) == ["what", "soil_cover", "climate_2026", "nutrients_pests", "unknowns"]
    assert all(part["evidence"] in ("measured", "validated", "modelled", "assumed") for part in ex.values())


def test_diversity_has_a_cost_so_the_ranking_is_a_real_trade_off():
    t = rt.compare(rt.CANDIDATES, ODDS)
    assert t.loc["SWC+clover", "crops_to_manage"] > t.loc["CS", "crops_to_manage"]
    simplicity_first = rt.weighted_ranking(t, {"crops_to_manage": 1})
    assert simplicity_first.index[0] == "CS"

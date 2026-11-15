"""Checks for fieldsense.canada: the Canada-wide rotation rule, growth timing and the scorecard."""
import numpy as np
import pandas as pd

from fieldsense import canada as ca


def curve(green_from, green_to, peak=0.8, base=0.15):
    """A daily greenness row: green between two days of the year, bare otherwise."""
    d = np.arange(1, 366)
    rise = 1 / (1 + np.exp(-(d - green_from) / 6))
    fall = 1 / (1 + np.exp((d - green_to) / 6))
    return base + (peak - base) * rise * fall


def test_rotation_rule_works_for_prairie_and_ontario_systems():
    assert ca.rotation_group([153, 146, 153, 146, 153]) == "simple"           # canola-wheat
    assert ca.rotation_group([147, 158, 147, 158, 158]) == "simple"           # corn-soybean
    assert ca.rotation_group([146, 131, 146, 131, 146]) == "simple"           # wheat-fallow
    assert ca.rotation_group([158, 145, 147, 158, 145]) == "diverse"          # soy-wheat-corn
    assert ca.rotation_group([153, 146, 162, 133, 153]) == "diverse"          # canola-wheat-peas-barley
    assert ca.rotation_group([122, 122, 147, 158, 122]) == "diverse"          # hay in an annual rotation
    assert ca.rotation_group([122] * 5) is None                               # permanent grassland
    assert ca.rotation_group([1, 2, 3, 147, 158]) is None                      # mostly unknown codes


def test_growth_timing_separates_the_five_classes():
    assert ca.timing_class(curve(115, 200)) == ca.WINTER                       # green in May, done by August
    assert ca.timing_class(curve(110, 280)) == ca.FORAGE                       # green all season
    assert ca.timing_class(curve(165, 225)) == ca.SPRING                       # peaks mid-July
    assert ca.timing_class(curve(185, 260)) == ca.SUMMER                       # peaks in August
    assert ca.timing_class(np.full(365, 0.2)) == ca.FALLOW
    row = curve(165, 225); row[:] = np.nan; row[150:160] = 0.6
    assert ca.timing_class(row) is None                                        # too few clear days


def test_cover_numbers_ignore_unseen_days():
    row = curve(185, 260)
    gappy = row.copy(); gappy[100:150] = np.nan                                # a cloudy spring
    full, gap = ca.cover_numbers([row]), ca.cover_numbers([gappy])
    assert 0.4 < full["bare_share_season"] < 0.7
    assert abs(gap["green_share_off_season"] - full["green_share_off_season"]) < 0.1


def test_scorecard_compares_diverse_with_simple_and_checks_timing():
    years = [2023, 2024, 2025]
    def field(i, group, rows, codes):
        m = pd.DataFrame(np.vstack(rows), index=years, columns=range(1, 366))
        return ca.field_record(i, f"F{i}", group, dict(zip(years, codes)), m)
    simple = [field(i, "simple", [curve(185, 260)] * 3, [147, 158, 147]) for i in (1, 2, 3)]
    diverse = [field(i, "diverse", [curve(115, 200), curve(110, 280), curve(185, 260)], [145, 122, 147]) for i in (4, 5, 6)]
    sc = ca.scorecard("on", simple + diverse)
    assert sc["timing"]["checked"] == 18 and sc["timing"]["share"] == 1.0
    assert sc["timing"]["evidence"] == "validated"
    bare = sc["cover"]["bare_share_season"]
    assert bare["diverse"] < bare["simple"] and bare["diff"]["diff"] < 0
    assert sc["name"] == "Ontario" and sc["n_simple"] == 3


def test_export_has_no_field_outlines(tmp_path):
    import json
    years = [2024, 2025]
    m = pd.DataFrame(np.vstack([curve(185, 260)] * 2), index=years, columns=range(1, 366))
    recs = {"mb": [ca.field_record(i, f"Manitoba field {i}", g, {2024: 153, 2025: 146}, m)
                   for i, g in ((1, "simple"), (2, "simple"), (3, "diverse"), (4, "diverse"))]}
    out = ca.export_canada(recs, tmp_path / "canada.json")
    data = json.loads((tmp_path / "canada.json").read_text())
    assert data["regions"][0]["name"] == "Manitoba" and len(data["regions"][0]["fields"]) == 4
    assert "lonlat" not in json.dumps(data) and out["all"]["n_diverse"] == 2



def test_export_never_writes_nan(tmp_path):
    years = [2024, 2025]
    m = pd.DataFrame(np.full((2, 365), np.nan), index=years, columns=range(1, 366))      # never seen
    recs = {"mb": [ca.field_record(i, f"F{i}", g, {2024: 153}, m) for i, g in ((1, "simple"), (2, "diverse"))]}
    ca.export_canada(recs, tmp_path / "c.json")
    txt = (tmp_path / "c.json").read_text()
    assert "NaN" not in txt and "Infinity" not in txt

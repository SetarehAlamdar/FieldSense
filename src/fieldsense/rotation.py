"""Rotation engine: compare crop rotations on soil cover, 2026 climate risk, nutrients and pests.

Lesson 7. Design choices (each one is a trade-off you should be able to defend):

1. DATA, NOT CODE, FOR AGRONOMY. Crop calendars and traits live in data/crops.json,
   so they can be checked and edited without touching Python.

2. A TRADE-OFF TABLE, NOT ONE MAGIC SCORE. Each rotation gets several metrics, each with
   its own evidence label. Turning them into one score needs WEIGHTS (how much does soil
   cover matter vs heat risk?), and weights are a farmer's values, not a fact. So:
   - `compare` returns the table;
   - `rank_robustness` asks: "under how many different weightings does each rotation
     come out best?" If one rotation wins under almost any weighting, the choice is robust.

3. MEASURED BEATS MODELLED. For a field's CURRENT rotation we already measured soil cover
   from the satellite barcode (Lesson 5). The calendar model is only needed for rotations
   the field hasn't tried, and its error on the current rotation tells us how far to trust it.

4. EXPLANATIONS ARE GENERATED FROM THE NUMBERS (templates, not free text), so the words
   can never say something the numbers don't support.
"""
import json
from dataclasses import dataclass, field
from importlib.resources import files

import numpy as np
import pandas as pd

SEASON = (60, 334)          # 1 Mar - 30 Nov, same window as phenology.cover_summary
MAIN_SEASON = (135, 273)    # main summer crop season, same as phenology.MAIN_SEASON
SPRING_BARE = (105, 166)    # 15 Apr - 15 Jun, same window as the heavy-rain indicator


def load_crop_table(path=None):
    """The crop table: from the package (default) or a file you edited."""
    text = open(path).read() if path else (files("fieldsense") / "data" / "crops.json").read_text()
    return json.loads(text)


@dataclass
class Rotation:
    """A repeating sequence of main crops, with an optional cover crop after some of them.

    covers = {index_in_sequence: cover_name}: the cover is sown after that year's crop
    and (if it overwinters) is green the next spring.
    """
    key: str
    name: str
    crops: list
    covers: dict = field(default_factory=dict)

    def __len__(self):
        return len(self.crops)


CANDIDATES = [
    Rotation("CS", "Corn - soybean", ["corn", "soybean"]),
    Rotation("CS+rye", "Corn - soybean + cereal rye after soybean", ["corn", "soybean"], {1: "cereal_rye"}),
    Rotation("SWC", "Soybean - winter wheat - corn", ["soybean", "winter_wheat", "corn"]),
    Rotation("SWC+clover", "Soybean - winter wheat + red clover - corn", ["soybean", "winter_wheat", "corn"],
             {1: "red_clover"}),
]


# ------------------------------------------------------------------ soil cover
def green_calendar(rot, table=None):
    """Boolean array (years x 366): is something green on each day of each rotation year?

    Wraps around: wheat is established the FALL BEFORE its year, and an overwintering cover
    is green the SPRING AFTER. Because the rotation repeats, "before year 0" is the last year.
    """
    t = table or load_crop_table()
    n = len(rot)
    g = np.zeros((n, 367), dtype=bool)          # index = day of year (1..366)

    def paint(year, windows):
        for a, b in windows:
            g[year % n, a:b + 1] = True

    for i, crop in enumerate(rot.crops):
        c = t["crops"][crop]
        paint(i, c["green"])
        paint(i - 1, c.get("green_previous_fall", []))
    for i, cover in rot.covers.items():
        c = t["covers"][cover]
        paint(i, c["green_fall"])
        paint(i + 1, c.get("green_next_spring", []))
    return g[:, 1:]


def cover_metrics(rot, table=None):
    """Modelled soil cover per average rotation year, in the same terms as the satellite barcode."""
    g = green_calendar(rot, table)
    doy = np.arange(1, 367)
    season = (doy >= SEASON[0]) & (doy <= SEASON[1])
    off = season & ~((doy >= MAIN_SEASON[0]) & (doy <= MAIN_SEASON[1]))
    spring = (doy >= SPRING_BARE[0]) & (doy <= SPRING_BARE[1])
    return {
        "green_share_season": float(g[:, season].mean()),
        "green_share_off_season": float(g[:, off].mean()),
        "spring_bare_share": float(1 - g[:, spring].mean()),
    }


# ------------------------------------------------------------------ climate exposure
def climate_exposure(rot, odds, table=None):
    """How often, per 100 crop-years, a risk hits a crop that's sensitive to it.

    exposure(risk) = average over rotation years of  P(risk in a season) x (crop exposed? 1 : 0)
    Heavy rain on bare soil uses the bare SHARE of the spring window instead of 0/1.
    A cover crop that needs fall warmth is exposed to the short-fall risk.
    `odds` = profile["climate_odds"] (Lesson 6).
    """
    t = table or load_crop_table()
    p = {k: r["share"] for k, r in odds["risks"].items()}
    out = {}
    for risk, prob in p.items():
        if risk == "heavy_rain_on_bare_soil":
            out[risk] = prob * cover_metrics(rot, t)["spring_bare_share"]
            continue
        hits = [prob if risk in t["crops"][c]["sensitive_to"] else 0.0 for c in rot.crops]
        for i, cover in rot.covers.items():
            if t["covers"][cover].get("needs_fall_warmth") == risk:
                hits[i] = max(hits[i], prob)
        out[risk] = float(np.mean(hits))
    out = {k: round(100 * v, 1) for k, v in out.items() if not k.startswith("short_fall_for_cover")}
    out["total"] = round(sum(out.values()), 1)
    return out


# ------------------------------------------------------------------ nutrients & pests
def agronomy_metrics(rot, table=None):
    """Simple, exact facts about the sequence itself (no data needed)."""
    t = table or load_crop_table()
    n = len(rot)
    legume_years = sum(t["crops"][c]["legume"] for c in rot.crops)
    legume_covers = sum(t["covers"][c]["legume"] for c in rot.covers.values())
    gaps = []
    for crop in set(rot.crops):
        idx = [i for i, c in enumerate(rot.crops) if c == crop]
        gaps += [((idx[(k + 1) % len(idx)] - i) % n) or n for k, i in enumerate(idx)]
    return {
        "years_in_cycle": n,
        "crop_families": len({t["crops"][c]["family"] for c in rot.crops}),
        "legume_share": round((legume_years + legume_covers) / n, 3),
        "min_years_between_same_crop": int(min(gaps)),
        "crops_to_manage": len(set(rot.crops)) + len(set(rot.covers.values())),
    }


# ------------------------------------------------------------------ compare & rank
CRITERIA = {   # metric -> direction (+1 higher is better, -1 lower is better)
    "green_share_off_season": +1,
    "spring_bare_share": -1,
    "climate_risk_total": -1,
    "legume_share": +1,
    "min_years_between_same_crop": +1,
    "crops_to_manage": -1,   # a COST: each extra crop means more equipment, markets, timing and know-how
}
# Not included because we have no data for them yet: yield, profit, labour. Their absence
# makes diverse rotations look better than they would to many farmers; say so in the demo.


def compare(candidates, odds, table=None):
    """The trade-off table: one row per rotation, one column per metric."""
    t = table or load_crop_table()
    rows = []
    for r in candidates:
        ex = climate_exposure(r, odds, t)
        rows.append({"key": r.key, "name": r.name, **cover_metrics(r, t),
                     "climate_risk_total": ex["total"],
                     **{f"risk_{k}": v for k, v in ex.items() if k != "total"},
                     **agronomy_metrics(r, t)})
    return pd.DataFrame(rows).set_index("key")


def _normalise(table, criteria):
    """Rescale each criterion to 0 (worst option) .. 1 (best option)."""
    out = pd.DataFrame(index=table.index)
    for col, sign in criteria.items():
        x = table[col].astype(float) * sign
        span = x.max() - x.min()
        out[col] = (x - x.min()) / span if span > 0 else 0.5
    return out


def weighted_ranking(table, weights, criteria=None):
    """One ranking for ONE set of weights (a farmer's priorities). Higher score = better."""
    criteria = criteria or CRITERIA
    norm = _normalise(table, criteria)
    w = pd.Series(weights, dtype=float).reindex(norm.columns).fillna(0)
    return (norm * (w / w.sum())).sum(axis=1).sort_values(ascending=False)


def rank_robustness(table, criteria=None, n=2000, seed=0):
    """Share of random weightings under which each rotation comes out best.

    Weights are drawn uniformly over all possible priority mixes (a Dirichlet(1,...,1)
    distribution): every way of splitting 100% of importance across the criteria is equally likely.
    """
    criteria = criteria or CRITERIA
    norm = _normalise(table, criteria).values
    w = np.random.default_rng(seed).dirichlet(np.ones(norm.shape[1]), size=n)
    winners = (w @ norm.T).argmax(axis=1)
    share = np.bincount(winners, minlength=len(table)) / n
    return pd.Series(share, index=table.index).sort_values(ascending=False)


# ------------------------------------------------------------------ the field's own rotation
def detect_current(history, recent_years=6):
    """Which candidate the field has been following, from the satellite history (profile["history"])."""
    recent = sorted(history, key=lambda h: h["year"])[-recent_years:]
    says = [h["satellite_says"] for h in recent]
    has_wheat = any(s.startswith("winter wheat") for s in says)
    has_cover = any("green after harvest" in s or "green in spring" in s for s in says)
    if has_wheat:
        return "SWC+clover" if has_cover else "SWC"
    return "CS+rye" if has_cover else "CS"


def next_crop(rotation_key, history, target_year=2026):
    """What the rotation puts in the field in target_year, if the satellite can tell."""
    rot = {r.key: r for r in CANDIDATES}[rotation_key]
    if "winter_wheat" not in rot.crops:
        return "corn or soybean (the satellite can't tell which; ask the farmer)"
    wheat_years = [h["year"] for h in history if h["satellite_says"].startswith("winter wheat")]
    if not wheat_years:
        return "unknown"
    pos = (rot.crops.index("winter_wheat") + target_year - max(wheat_years)) % len(rot)
    return rot.crops[pos].replace("_", " ")


# ------------------------------------------------------------------ explanation
def explain(row, current_key, evidence, measured_cover=None):
    """Five-part explanation for one rotation, built only from its numbers.

    row: one row of `compare`; evidence: {part: label}; measured_cover: optional
    {"green_share_off_season", "spring_bare_share"} measured by satellite for the CURRENT rotation.
    """
    cover_source = "measured by satellite" if measured_cover else "estimated from a crop calendar"
    cov = measured_cover or row
    risks = {k[5:]: v for k, v in row.items() if k.startswith("risk_") and v > 0}
    top = max(risks, key=risks.get) if risks else None
    return {
        "what": {"text": f"{row['name']}: a {int(row['years_in_cycle'])}-year cycle"
                         + (" (what this field does now)." if row.name == current_key else "."),
                 "evidence": evidence.get("what", "measured" if row.name == current_key else "assumed")},
        "soil_cover": {"text": f"Living cover on {100*cov['green_share_off_season']:.0f}% of off-season days; "
                               f"soil bare on {100*cov['spring_bare_share']:.0f}% of spring days (15 Apr-15 Jun), "
                               f"{cover_source}.",
                       "evidence": evidence.get("soil_cover", "modelled")},
        "climate_2026": {"text": f"About {row['climate_risk_total']:.0f} risk-hits per 100 crop-years in 2026 odds"
                                 + (f"; the largest is {top.replace('_', ' ')} ({risks[top]:.0f} per 100)." if top else "."),
                         "evidence": evidence.get("climate_2026", "assumed")},
        "nutrients_pests": {"text": f"{int(row['crop_families'])} crop families; legumes in "
                                    f"{100*row['legume_share']:.0f}% of years; the same crop returns every "
                                    f"{int(row['min_years_between_same_crop'])} years at the shortest.",
                            "evidence": evidence.get("nutrients_pests", "assumed")},
        "unknowns": {"text": "Yield and profit are not estimated; wheat-specific risks (winterkill, wet-June disease) "
                             "are not modelled; crop calendars are rules of thumb.",
                     "evidence": "assumed"},
    }

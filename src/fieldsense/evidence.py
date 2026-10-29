"""Evidence: every number FieldSense shows says where it came from and how far to trust it.

This is the data behind the "evidence passport". Four labels, from strongest to weakest:

  measured   Observed directly at this field: a ground instrument, or satellite pixels
             inside the field (e.g. HLS greenness).
  validated  Derived or modelled, AND checked against independent ground truth, with the
             test result recorded (e.g. NASA POWER rainfall corrected and tested against
             Environment Canada stations on held-out years).
  modelled   From a model or prediction not checked at this field (e.g. SoilGrids,
             SMAP Level 4).
  assumed    From literature or an expert rule, not tested here (e.g. a crop's water use
             from FAO-56 tables).

Why this matters: the challenge asks each recommendation to state its evidence and its
information gaps. If every number carries a label, the app can say both automatically.
"""
import json
import math
from dataclasses import asdict, dataclass

LABELS = {
    "measured": "Observed directly at this field (ground instrument, or satellite pixels inside the field).",
    "validated": "Derived or modelled, and checked against independent ground truth; test result recorded.",
    "modelled": "From a model or prediction not checked at this field.",
    "assumed": "From literature or an expert rule; not tested here.",
}
STRENGTH = {"measured": 4, "validated": 3, "modelled": 2, "assumed": 1}


@dataclass
class Evidence:
    """One piece of evidence, written so a farmer or a judge can read it."""
    id: str            # short key, e.g. "power_precip_correction"
    label: str         # one of LABELS
    claim: str         # plain-language sentence: what we know
    source: str        # dataset or reference
    test: str = ""     # how it was checked (empty for modelled / assumed)
    result: str = ""   # the check's outcome, e.g. "error -26% -> -5%"
    caveat: str = ""   # the honest limitation

    def __post_init__(self):
        if self.label not in LABELS:
            raise ValueError(f"label must be one of {list(LABELS)}, got {self.label!r}")
        if self.label == "validated" and not (self.test and self.result):
            raise ValueError("'validated' evidence must say how it was tested and what the result was")


class EvidenceRegistry:
    """A collection of Evidence, saved as JSON so the API and website can read it."""

    def __init__(self):
        self.items = {}

    def add(self, evidence):
        self.items[evidence.id] = evidence
        return evidence

    def get(self, evidence_id):
        return self.items[evidence_id]

    def weakest(self, ids):
        """The weakest label among several pieces of evidence: a chain is only as strong as its weakest link."""
        return min((self.items[i].label for i in ids), key=STRENGTH.get)

    def to_json(self, path):
        with open(path, "w") as f:
            json.dump({"labels": LABELS, "evidence": [asdict(e) for e in self.items.values()]}, f, indent=2)

    @classmethod
    def from_json(cls, path):
        reg = cls()
        with open(path) as f:
            for e in json.load(f)["evidence"]:
                reg.add(Evidence(**e))
        return reg

    def table(self):
        import pandas as pd
        return pd.DataFrame([asdict(e) for e in self.items.values()])


def value(mid, low=None, high=None, unit="", evidence=None, range_meaning=""):
    """How FieldSense stores every number: a middle value, a range, a unit, and its evidence.

    range_meaning says what low/high mean, e.g. "10th-90th percentile across years"
    or "90% prediction interval". A number with no stated range is a warning sign.
    """
    clean = lambda v: None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 3)
    mid, low, high = clean(mid), clean(low), clean(high)
    if None not in (low, mid, high) and not (low <= mid <= high):
        raise ValueError(f"expected low <= mid <= high, got {low}, {mid}, {high}")
    return {"mid": mid, "low": low, "high": high, "unit": unit,
            "range_meaning": range_meaning, "evidence": evidence}

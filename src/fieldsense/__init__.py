"""FieldSense: field-level crop rotation decision support from NASA Earth observations.

Light imports only: `import fieldsense as fs` must work without the satellite extras
(rasterio, earthaccess). Data sources are imported from `fieldsense.sources.<name>`.
"""
__version__ = "0.2.0"

from .climate import (RISKS, apply_monthly_offsets, frost_dates, held_out_offset_check, indicators_by_year,
                      make_futures, monthly_offsets, risk_counts, warming_trend)
from .correction import apply_monthly_scaling, factors_from, held_out_error, monthly_scaling_factors
from .evidence import LABELS, Evidence, EvidenceRegistry, value
from .phenology import barcode_matrix, cover_summary, crop_label, daily_ndvi, field_history
from .profile import (build_field_profile, check_profile, climate_odds, climate_summary, load_profile,
                      save_profile, soil_moisture_summary, soil_summary)

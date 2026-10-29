"""FieldSense: field-level crop rotation decision support from NASA Earth observations.

Light imports only: `import fieldsense as fs` must work without the satellite extras
(rasterio, earthaccess). Data sources are imported from `fieldsense.sources.<name>`.
"""
__version__ = "0.1.0"

from .correction import apply_monthly_scaling, factors_from, held_out_error, monthly_scaling_factors
from .evidence import LABELS, Evidence, EvidenceRegistry, value
from .phenology import barcode_matrix, cover_summary, crop_label, daily_ndvi, field_history
from .profile import (build_field_profile, check_profile, climate_summary, load_profile,
                      save_profile, soil_moisture_summary, soil_summary)

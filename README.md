# FieldSense

**Field-level crop rotation decision support from NASA Earth observations.**
Built for the NASA Space Apps Challenge 2026.

FieldSense reads a field's past from space (what grew, when the soil was bare, how
wet and warm the seasons were), compares rotation options, and shows how sure it is
about every number. Each number is stored with a range and an *evidence label*:

| Label | Meaning | Example |
|---|---|---|
| **Measured** | Observed directly at this field | HLS greenness inside the field |
| **Validated** | Modelled, then checked against independent ground truth | NASA POWER rainfall, corrected and tested against Environment Canada stations on held-out years |
| **Modelled** | From a model not checked at this field | SoilGrids soil texture, SMAP L4 soil moisture |
| **Assumed** | From literature or expert rules | Crop water use from FAO-56 tables |

## Repository layout

```
src/fieldsense/
  sources/        one module per data source (download + cache)
    power.py        NASA POWER daily weather
    stations.py     Environment Canada weather stations (ground truth)
    soilgrids.py    ISRIC SoilGrids soil properties with uncertainty
    appeears.py     NASA AppEEARS (SMAP L4 soil moisture)
    hls.py          NASA HLS Landsat/Sentinel-2 field greenness (needs the [hls] extra)
  correction.py   bias correction of model rainfall, with held-out validation
  phenology.py    crop history, field barcode, living-cover metrics from greenness
  evidence.py     evidence labels and registry (the "evidence passport")
  profile.py      the field profile: one JSON per field, read by the API and website
  viz.py          figures for the demo
tests/            automated checks (run: pytest)
notebooks/        teaching notebooks that build the data step by step
```

## Install

```bash
pip install "git+https://github.com/SetarehAlamdar/FieldSense.git"          # core
pip install "fieldsense[hls] @ git+https://github.com/SetarehAlamdar/FieldSense.git"   # + satellite reading
```

For development (editable install, so code changes apply without reinstalling):

```bash
git clone https://github.com/SetarehAlamdar/FieldSense.git
cd FieldSense
pip install -e ".[dev]"
pytest
```

## Data policy

- **No private data in this repository.** Partner field records and survey boundaries live
  in a private folder (`private/`, ignored by git) and are used only to compute *aggregate*
  validation scores. Only the scores are published.
- **No credentials in code.** NASA Earthdata logins come from environment variables or
  Colab Secrets.
- Downloaded data is cached locally (`data_cache/`, ignored by git) and can be re-downloaded.

## Data sources and citations

- NASA POWER Project, NASA Langley Research Center. https://power.larc.nasa.gov
- Masek, J., et al. HLS Operational Land Surface Reflectance and TOA Brightness Daily Global
  30 m v2.0 (HLSL30, HLSS30). NASA EOSDIS LP DAAC. https://doi.org/10.5067/HLS/HLSL30.002,
  https://doi.org/10.5067/HLS/HLSS30.002
- Reichle, R., et al. SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil
  Moisture Geophysical Data, Version 8 (SPL4SMGP). NASA NSIDC DAAC.
- AppEEARS Team. Application for Extracting and Exploring Analysis Ready Samples. NASA LP DAAC.
  https://appeears.earthdatacloud.nasa.gov
- Poggio, L., et al. (2021). SoilGrids 2.0. *SOIL*, 7, 217–240. https://doi.org/10.5194/soil-7-217-2021
- Environment and Climate Change Canada, Historical Climate Data (stations 4760, 41983).
  https://climate.weather.gc.ca
- Field validation: Elora Research Station long-term rotation plots, University of Guelph
  (aggregate results only, with permission).

## License

Apache License 2.0. See [LICENSE](LICENSE).

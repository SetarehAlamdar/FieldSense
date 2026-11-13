# FieldSense

[![tests](https://github.com/SetarehAlamdar/FieldSense/actions/workflows/tests.yml/badge.svg)](https://github.com/SetarehAlamdar/FieldSense/actions/workflows/tests.yml)

**A field's past, read from NASA satellites and climate data, to choose its next crop rotation, with the evidence behind every number.**

NASA Space Apps Challenge 2026 · Demo site: https://setarehalamdar.github.io/FieldSense/

## What it does

For each field, FieldSense:

1. **Reads its history from space.** NASA HLS (Landsat + Sentinel-2) greenness since 2015 shows what grew each year and when the soil was bare: the **field barcode**.
2. **Measures living soil cover.** It counts how many days the soil was covered outside the main crop season (cover crops, winter wheat) and how often it was bare when spring storms hit.
3. **Gives the odds for next season.** 1,000 possible 2026 seasons are built from 30 years of NASA POWER weather, corrected against Environment Canada stations. Risks are shown as "X in 100 seasons" next to how often they really happened.
4. **Compares rotations as a trade-off table**, not one magic score: soil cover, climate exposure, nutrients and pest breaks, and management effort. It also shows how robust the choice is across 2,000 different ways of weighing those criteria.
5. **Labels every number with its evidence**, so users see how far to trust it:

| Label | Meaning | Example |
|---|---|---|
| **Measured** | Observed directly at this field | HLS greenness inside the field |
| **Validated** | Modelled, then checked against independent ground truth | POWER rainfall and temperature, corrected and tested against stations on held-out years |
| **Modelled** | From a model not checked at this field | SoilGrids soil texture, SMAP L4 soil moisture |
| **Assumed** | From literature or expert rules | Risk thresholds, crop calendars |

The pilot site is the Elora Research Station (Ontario, Canada): two simple corn–soybean plots and two diverse soybean–wheat–corn plots with cover crops. How the data is produced and checked is described in [METHODS.md](METHODS.md).

## Repository layout

```
src/fieldsense/
  sources/          one module per data source (download + cache)
    power.py          NASA POWER daily weather
    stations.py       Environment Canada weather stations (ground truth)
    soilgrids.py      ISRIC SoilGrids soil properties with uncertainty
    appeears.py       NASA AppEEARS (SMAP L4 soil moisture)
    hls.py            NASA HLS field greenness (needs the [hls] extra)
  correction.py     rainfall bias correction with held-out validation
  climate.py        temperature correction, climate indicators, 2026 futures and risk odds
  phenology.py      crop history, field barcode, living-cover metrics
  rotation.py       rotation comparison, robustness, explanations
  data/crops.json   crop calendar and traits (editable data, not code)
  evidence.py       evidence labels and registry ("evidence passport")
  profile.py        field profile: one JSON per field (the data contract)
  export.py         public, privacy-checked copy of the data for the website
  viz.py            figures
docs/               the demo website (GitHub Pages); data files in docs/data/
tests/              automated checks (run: pytest)
```

## Quick start

```bash
git clone https://github.com/SetarehAlamdar/FieldSense.git
cd FieldSense
pip install -e ".[dev]"      # add [hls] to read satellite images
pytest                       # all tests should pass
```

Preview the website locally (it needs the data files in `docs/data/`):

```bash
cd docs && python -m http.server 8000     # then open http://localhost:8000
```

## Contributing (team)

- **Work on a branch and open a pull request.** Don't push to `main`; every merge to `main` updates the live site.
- **Tests must pass** before merging. They run automatically on every pull request (GitHub Actions); run `pytest` locally first. Add a test when you add or fix behaviour.
- **The website reads only the field profile JSON** (schema 0.3, see `profile.py`). Page changes go in `docs/` (`index.html` for text, `app.js` for each section's drawing, `style.css` for looks).
- **Agronomy values live in `src/fieldsense/data/crops.json`** and the risk thresholds in `climate.RISKS`. Changes to them should say where the new value comes from.

## Data policy

- **No private data in this repository.** Partner field records and survey boundaries are kept outside the repository and used only to compute *aggregate* validation scores (e.g. "winter wheat found in 2 of 2 wheat years"). Only the scores are published.
- **The website gets a privacy-checked copy** (`export.py`): coordinates rounded to about 1 km, plot areas removed, and a check that refuses to publish anything that still looks private.
- **No credentials in code.** NASA Earthdata logins come from environment variables or notebook secrets.
- `private/`, `data_cache/`, `profiles/` and `.env` are ignored by git.

## Data sources and citations

- NASA POWER Project, NASA Langley Research Center. https://power.larc.nasa.gov
- Masek, J., et al. HLS Operational Land Surface Reflectance and TOA Brightness Daily Global 30 m v2.0 (HLSL30, HLSS30). NASA EOSDIS LP DAAC. https://doi.org/10.5067/HLS/HLSL30.002, https://doi.org/10.5067/HLS/HLSS30.002
- Reichle, R., et al. SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture Geophysical Data, Version 8 (SPL4SMGP). NASA NSIDC DAAC.
- AppEEARS Team. Application for Extracting and Exploring Analysis Ready Samples. NASA LP DAAC. https://appeears.earthdatacloud.nasa.gov
- Poggio, L., et al. (2021). SoilGrids 2.0. *SOIL*, 7, 217–240. https://doi.org/10.5194/soil-7-217-2021
- Environment and Climate Change Canada, Historical Climate Data (stations 4760, 41983). https://climate.weather.gc.ca
- Field validation: Elora Research Station long-term rotation plots, University of Guelph (aggregate results only, with permission).

## License

Apache License 2.0. See [LICENSE](LICENSE).

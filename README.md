# FieldSense

[![tests](https://github.com/SetarehAlamdar/FieldSense/actions/workflows/tests.yml/badge.svg)](https://github.com/SetarehAlamdar/FieldSense/actions/workflows/tests.yml)

**A field's past, read from NASA satellites and climate data, to choose its next crop rotation, anywhere in Canada, with the evidence behind every number.**

NASA Space Apps Challenge 2026 · Team Star Farmer · Challenge: *Field Shift: Adapting Farms with NASA Data*

- **Demo site:** https://setarehalamdar.github.io/FieldSense/
- **Try your own field (web app, no login):** https://huggingface.co/spaces/SetarehAlamdar/fieldsense
- **Run it yourself in Colab:** [notebooks/FieldSense_My_Field.ipynb](https://colab.research.google.com/github/SetarehAlamdar/FieldSense/blob/main/notebooks/FieldSense_My_Field.ipynb)

## What it does

For a field anywhere in Canada, FieldSense:

1. **Finds it on Canada's crop map.** Click a field (or give a location): the AAFC Annual Crop Inventory gives the field's outline and its crop every year, and a rule that works in every province groups rotations into *simple* (at most two crops, no forage: corn–soybean, canola–wheat, wheat–fallow) and *diverse* (three or more crops, or hay).
2. **Reads its history from space.** Every clear NASA HLS (Landsat + Sentinel-2, 30 m) image becomes a **field barcode**: one row per year, brown when the soil is bare, green when plants grow. From *when* it is green, FieldSense reads the crop type (winter cereal, spring crop, summer crop, forage, fallow) and checks itself against the crop map.
3. **Measures living soil cover:** bare days in the season, bare days in spring storm season, green days outside summer.
4. **Gives the odds for next season (2027).** NASA POWER weather (30 years) corrected with the **nearest Environment Canada station**, found automatically, then 1,000 possible seasons. Risks are shown as "X in 100 seasons" next to how often they really happened.
5. **Compares rotations as a trade-off table**, not one magic score, with how robust the choice is across 2,000 ways of weighing the criteria, and five-part explanations.
6. **Labels every number with its evidence**, so users see how far to trust it:

| Label | Meaning | Example |
|---|---|---|
| **Measured** | Observed directly at this field | HLS greenness inside the field |
| **Validated** | Modelled, then checked against independent ground truth | POWER rainfall and temperature, corrected and tested against stations on held-out years; crop timing vs the crop map |
| **Modelled** | From a model not checked at this field | SoilGrids soil texture, SMAP L4 soil moisture |
| **Assumed** | From literature or expert rules | Risk thresholds, crop calendars |

## Results

- **Elora Research Station** (10-year rotation trial, Ontario): the crops read from space match the field records; the diverse rotation had living cover on 39% of off-season days, the simple one on 3%.
- **Across Canada:** 42 farm fields in 6 locations in Alberta, Saskatchewan, Manitoba, Ontario and Quebec. Crop timing agreed with the crop map in **177 of 210 field-years (84%)**; every location passed the rule set in advance (≥ 80%). Diverse fields were bare **7 points less** of the season (90% field-bootstrap interval 1 to 13). In Ontario and Quebec diversity adds off-season cover (winter wheat, hay); on the Prairies both groups are almost never green outside summer.

How the data is produced and checked is described in [METHODS.md](METHODS.md).

## Repository layout

```
src/fieldsense/
  sources/          one module per data source (download + cache)
    power.py          NASA POWER daily weather
    stations.py       Environment Canada weather stations (ground truth)
    soilgrids.py      ISRIC SoilGrids soil properties with uncertainty
    appeears.py       NASA AppEEARS (SMAP L4 soil moisture)
    hls.py            NASA HLS field greenness (needs the [hls] extra)
    hls_views.py      satellite pictures: fields in their surroundings, a year of pictures
    aci.py            AAFC Annual Crop Inventory: finding fields, crop per year
  correction.py     rainfall bias correction with held-out validation
  climate.py        temperature correction, climate indicators, futures and risk odds
  phenology.py      crop history, field barcode, living-cover metrics
  rotation.py       rotation comparison, robustness, explanations (next season: 2027)
  canada.py         Canada-wide rotation rule, growth-timing classes, regional scorecards
  anywhere.py       any location: nearest ECCC station, corrected POWER, 2027 odds
  myfield.py        one farmer's field: the field at a point, its history, rotation advice
  data/crops.json   crop calendar and traits (editable data, not code)
  evidence.py       evidence labels and registry ("evidence passport")
  profile.py        field profile: one JSON per field (the data contract)
  export.py         public, privacy-checked copy of the data for the website
  viz.py            figures
docs/               the demo website (GitHub Pages); data files in docs/data/
space/              the web app (Gradio, Hugging Face Spaces)
notebooks/          FieldSense_My_Field.ipynb: any field, in Colab
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
- Environment and Climate Change Canada, Historical Climate Data (daily station records; at Elora stations 4760 and 41983) and the climate station list (api.weather.gc.ca). https://climate.weather.gc.ca
- Agriculture and Agri-Food Canada, Annual Crop Inventory (2015–2025), 30 m. https://open.canada.ca
- Map imagery on the website: Esri World Imagery (Esri, Maxar, Earthstar Geographics); backup: Sentinel-2 cloudless by EOX IT Services (contains modified Copernicus Sentinel data 2020). Map library: Leaflet.
- Field validation: Elora Research Station long-term rotation plots, University of Guelph (aggregate results only, with permission).

## License

Apache License 2.0. See [LICENSE](LICENSE).

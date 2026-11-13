# FieldSense methods

How each part of the data is produced and checked. Every step is a function in `src/fieldsense/`; the pilot site is the Elora Research Station, Ontario (four rotation plots).

## 1. Weather: NASA POWER, corrected and validated

- **Source:** NASA POWER daily point data (`sources/power.py`), about 50 km resolution, 1996–2025.
- **Rainfall** (`correction.py`): POWER read about 25% low at Elora. Each day is multiplied by a monthly factor (station mean / POWER mean for that calendar month), fitted against ECCC Fergus Shand Dam (4760). Multiplicative, because a dry day must stay dry and the shortfall scales with the amount.
  - *Validation:* factors fitted on 1996–2010, tested on 2011–2025 → **error after correction −4.7%**. A second station (Elora RCS, 41983) is used as a cross-check; it reads lower in winter (automatic gauges under-catch snow).
- **Temperature** (`climate.py`): additive monthly offsets (station − POWER) against Elora RCS (41983), at the research station itself. Additive, because a 1 °C warm bias is the same at −10 °C and +10 °C.
  - *Validation:* fitted 2004–2014, tested 2015–2025. Bias: min **+0.98 → +0.09 °C**, max **+0.95 → +0.11 °C**. Frost-free-days error **+11 → +4 days** (station median 153 days, corrected POWER 154).
- Months with less than 90% of days reported are excluded from all station comparisons.

## 2. Field history: NASA HLS greenness

- **Source:** HLS v2.0 L30 (Landsat 8/9) and S30 (Sentinel-2), 30 m (`sources/hls.py`). Only the pixels inside each plot are read; plots are shrunk inward by 30 m so no pixel mixes neighbouring fields. Clouds, shadows, snow and water are removed with the Fmask quality layer.
- **Greenness:** NDVI per clear look. Same-day Landsat and Sentinel looks are averaged, and a 3-look rolling median removes single bad looks (`phenology.py`).
- **Crop label per year:** winter wheat peaks in June (before day 195), corn and soybean from late July; the main peak is searched up to mid-August. Green in spring or after harvest flags a cover crop. Corn and soybean are deliberately not separated (greenness alone can't tell them apart reliably).
  - *Validation:* against partner field records 2015–2021 → **winter wheat found in 2 of 2 wheat plot-years; corn/soybean correct in 26 of 26**. Caveats: few wheat cases, and thresholds were tuned at this site.
- **Field barcode:** daily NDVI by straight-line interpolation between clear looks; gaps longer than 30 days stay empty (never invented). One row per year, 365 days.
- **Living cover** (1 Mar–30 Nov): bare = NDVI < 0.30, green = NDVI ≥ 0.40. Shares are computed over observed days only, so cloudy years aren't counted as bare.

## 3. Soil and soil moisture

- **Soil** (`sources/soilgrids.py`): ISRIC SoilGrids 2.0, 250 m, 0–30 cm thickness-weighted, with the 5%–95% prediction interval. Labelled **Modelled**: it's a prediction, not a sample.
- **Soil moisture** (`sources/appeears.py`): NASA SMAP L4 (SPL4SMGP v8) root-zone moisture via AppEEARS, 9 km. Labelled **Modelled**.

## 4. Climate odds for 2026

- **Indicators per year** (`climate.year_indicators`): frost dates and frost-free days, growing degree days, days ≥ 32 °C during corn pollination (10 Jul–10 Aug), 25 mm+ rain days while fields are bare (15 Apr–15 Jun), longest summer dry spell, fall warmth after soybean harvest.
- **Warming trend:** annual mean temperature 1996–2025 = **+0.39 °C/decade (90% bootstrap CI +0.09 to +0.67)**. Pre-set rule: shift past years to 2026 warmth only if the whole interval is above 0 (it is).
- **Futures** (`climate.make_futures`): 1,000 seasons, each a whole past year (a year-block bootstrap keeps dry spells and hot-dry combinations intact), shifted by the trend, with rain × (1 + N(0, 0.10)) and temperature + N(0, residual sd) for remaining data uncertainty. Fixed seed for reproducibility.
- **Odds** are reported as "X in 100 seasons" next to the count in the 30 real years. 1,000 futures keep Monte Carlo error to about ±1.3 points per 100 (with 100 futures it was up to ±15).
- Risk thresholds are agronomic rules of thumb, labelled **Assumed**. The odds therefore carry the label *assumed*: a chain is only as strong as its weakest link.

## 5. Rotation comparison

- **Candidates** (`rotation.py`): corn–soybean; corn–soybean + cereal rye; soybean–winter wheat–corn; soybean–winter wheat + red clover–corn.
- **Metrics:** off-season living cover, bare share in spring, 2026 climate exposure (risk probability × crop sensitivity, averaged over the cycle), legume share, years between the same crop, crops to manage (a cost).
- **Soil cover for rotations a field hasn't tried** comes from a crop-calendar model (`data/crops.json`). For the field's current rotation the satellite measurement is used instead. The model is compared with satellite measurements on the two rotations grown at Elora, with a 10-point acceptance rule set in advance.
- **Robustness:** 2,000 random weightings of the criteria (Dirichlet(1,…,1)); the share of weightings under which each rotation is best. Yield, profit and labour are not included yet, which favours diverse rotations; this is stated on the page.
- **Explanations** are generated from the numbers by templates, five parts each, with the evidence label of each part.

## 6. Publishing

`export.py` makes the public copy for the website: coordinates rounded to 2 decimals (about 1 km), plot areas and the survey source removed, barcode numbers added. `check_public` refuses to write any file that still looks private.

## Known gaps

- Corn and soybean are not separated from greenness; the farmer's record is needed.
- Soil is a 250 m prediction with a wide organic-carbon range; a lab soil test would replace it.
- Soil moisture is one value per 9 km square.
- Crop rules and calendars were tuned at Elora; accuracy elsewhere is unknown until checked there.
- Yield, profit and labour are not yet part of the rotation comparison.

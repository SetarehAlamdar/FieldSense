---
title: FieldSense
emoji: 🌱
colorFrom: green
colorTo: indigo
sdk: gradio
sdk_version: 4.44.1
python_version: "3.10"
app_file: app.py
pinned: false
license: apache-2.0
short_description: Field history from NASA satellites + rotation choice
---

# FieldSense: your field, anywhere in Canada

Type a location: FieldSense finds the field at that point on Canada's crop map (AAFC Annual Crop Inventory), reads every clear NASA HLS image of it, corrects NASA POWER weather with the nearest Environment Canada station, and shows the field's history, soil cover, 2027 weather odds and which rotation and why.

**Space secrets needed:** `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` (a free NASA Earthdata account).

Code: https://github.com/SetarehAlamdar/FieldSense (Apache 2.0). NASA Space Apps 2026, Team Star Farmer.

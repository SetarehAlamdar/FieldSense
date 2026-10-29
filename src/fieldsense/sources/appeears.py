"""NASA AppEEARS: point time series cut out of large archives (used for SMAP in Lesson 3).

Asynchronous jobs: log in -> submit task (get a ticket) -> poll status -> download.
Lesson learned: 10 years of 3-hourly SMAP Level 4 means ~31,000 files on NASA's side
and took ~8 hours. The cost of a query depends on how the data is STORED, not on how
much comes back. Use this for pre-computing demo sites, never inside a live request.
"""
import os
import time
import requests

API = "https://appeears.earthdatacloud.nasa.gov/api"

def login(username, password):
    """Exchange Earthdata credentials for a temporary token."""
    r = requests.post(f"{API}/login", auth=(username, password), timeout=60)
    r.raise_for_status()
    return r.json()["token"]

def latest_product(prefix):
    """Newest version of a product, e.g. 'SPL4SMGP' -> 'SPL4SMGP.008'. Discover it, don't hard-code it."""
    r = requests.get(f"{API}/product", timeout=60)
    r.raise_for_status()
    names = sorted(p["ProductAndVersion"] for p in r.json()
                   if p["ProductAndVersion"].startswith(prefix + "."))
    if not names:
        raise ValueError(f"No AppEEARS product starts with {prefix}")
    return names[-1]

def layers(product):
    """Names of all layers (variables) available in a product."""
    r = requests.get(f"{API}/product/{product}", timeout=60)
    r.raise_for_status()
    return list(r.json().keys())

def submit_point_task(token, name, product, layer_names, lat, lon, start, end, point_id="farm"):
    """Ask AppEEARS for a time series at one point. Dates are MM-DD-YYYY. Returns the task ID."""
    task = {
        "task_type": "point",
        "task_name": name,
        "params": {
            "dates": [{"startDate": start, "endDate": end}],
            "layers": [{"product": product, "layer": l} for l in layer_names],
            "coordinates": [{"latitude": lat, "longitude": lon, "id": point_id}],
        },
    }
    r = requests.post(f"{API}/task", json=task,
                      headers={"Authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    return r.json()["task_id"]

def wait_for_task(token, task_id, poll_seconds=30, max_minutes=120):
    """Check the task status until it is done (or failed, or we run out of patience)."""
    headers = {"Authorization": f"Bearer {token}"}
    started = time.time()
    while True:
        r = requests.get(f"{API}/task/{task_id}", headers=headers, timeout=60)
        r.raise_for_status()
        status = r.json().get("status")
        print(time.strftime("%H:%M:%S"), "status:", status)
        if status == "done":
            return
        if status == "error":
            raise RuntimeError(f"AppEEARS task failed: {r.json()}")
        if time.time() - started > max_minutes * 60:
            raise TimeoutError("Still not done. Re-run this cell later; it will pick up the same task.")
        time.sleep(poll_seconds)

def download_results(token, task_id, out_dir):
    """Download every CSV file the task produced. Returns their paths."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API}/bundle/{task_id}", headers=headers, timeout=60)
    r.raise_for_status()
    paths = []
    for f in r.json()["files"]:
        if not f["file_name"].endswith(".csv"):
            continue
        path = os.path.join(out_dir, os.path.basename(f["file_name"]))
        with requests.get(f"{API}/bundle/{task_id}/{f['file_id']}", headers=headers,
                          stream=True, allow_redirects=True, timeout=300) as d:
            d.raise_for_status()
            with open(path, "wb") as fh:
                for chunk in d.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
        paths.append(path)
    return paths

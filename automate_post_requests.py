import json
import time
from pathlib import Path

try:
    import requests
except ImportError:
    raise SystemExit("Missing 'requests'. Install with: pip install requests")

# ======= minimal settings =======
API_URL = "http://127.0.0.1:8000/parse"  # <- set your endpoint
REPOS_FILE = "repos.json"
OUT_FILE = "new.json"
CHOICES = ["1", "2", "3", "4", "5"]      # five language flags
DELAY_SEC = 0.2                          # delay between requests
# =================================

# 1) Build new.json as a JSON array 
# We use 5 languages per repo. 
# In this way, we automate the parsing proccess and we don't look for the codebase's programming language
repos_path = Path(REPOS_FILE)
if not repos_path.exists():
    raise FileNotFoundError(f"repos file not found: {repos_path}")

repos = json.loads(repos_path.read_text(encoding="utf-8"))
if not isinstance(repos, list):
    raise ValueError("repos.json must be a JSON array of strings (repo URLs).")

data = [{"choice": ch, "repo_url": repo}
        for repo in repos if isinstance(repo, str)
        for ch in CHOICES]

Path(OUT_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Created {OUT_FILE} with {len(data)} items (5 per repo).")

# 2) Read new.json and send sequential POST requests (NO TIMEOUT)
payloads = json.loads(Path(OUT_FILE).read_text(encoding="utf-8"))
headers = {"Content-Type": "application/json"}

for i, payload in enumerate(payloads, start=1):
    payload["choice"] = str(payload.get("choice"))
    try:
        # no 'timeout' argument -> wait indefinitely for response
        resp = requests.post(API_URL, headers=headers, json=payload)
        print(f"[{i}] POST {payload} -> HTTP {resp.status_code}")
        resp.raise_for_status()
        # print(resp.text)  # uncomment if you want to see body
    except requests.RequestException as e:
        print(f"[{i}] Request error: {e}")
    time.sleep(DELAY_SEC)

print("All requests completed.")

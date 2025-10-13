import json
import time
from pathlib import Path

try:
    import requests
except ImportError:
    raise SystemExit("Missing 'requests'. Install with: pip install requests")

try:
    from pymongo import MongoClient, errors
except ImportError:
    raise SystemExit("Missing 'pymongo'. Install with: pip install pymongo")

# ======= minimal settings =======
API_URL = "http://127.0.0.1:8000/parse"  # <- set your endpoint
REPOS_FILE = "repos.json"
OUT_FILE = "new.json"
CHOICES = ["1", "2", "3", "4", "5"]      # five language flags
DELAY_SEC = 0.2                          # delay between requests

MONGO_URI  = "mongodb://127.0.0.1:27017"
DB_NAME    = "repos_db"
COLL_NAME  = "seen_repos"
# ======================================

# --- MongoDB: connection + unique index ---
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client[DB_NAME]
coll = db[COLL_NAME]
coll.create_index("repo_url", unique=True)

# 1) Build new.json as a JSON array 
# We use 5 languages per repo. 
# In this way, we automate the parsing proccess and we don't look for the codebase's programming language
repos_path = Path(REPOS_FILE)
if not repos_path.exists():
    raise FileNotFoundError(f"repos file not found: {repos_path}")

repos = json.loads(repos_path.read_text(encoding="utf-8"))
if not isinstance(repos, list):
    raise ValueError("repos.json must be a JSON array of strings (repo URLs).")

# Ensure only strings go to Mongo's $in
repos = [r.strip() for r in repos if isinstance(r, str) and r.strip()]
repos = list(dict.fromkeys(repos))  # keep order, remove duplicates

# --- find the repo links that already exist in MongoDB ---
existing = {
    d["repo_url"]
    for d in coll.find({"repo_url": {"$in": repos}}, {"_id": 0, "repo_url": 1})
}

# --- Keep only the new repo links in the JSON file and rewrite the JSON file without the old links ---
new_repos = [r for r in repos if r not in existing]
repos_path.write_text(json.dumps(new_repos, ensure_ascii=False, indent=2), encoding="utf-8")

# --- Save the new repo links in the Mongo Database ---
if new_repos:
    docs = [{"repo_url": r} for r in new_repos]
    coll.insert_many(docs, ordered=False)

# --- If no new repo links exist, then stop ---
if not new_repos:
    print("No new repos have been found (all the repo urls inside the JSON file are already saved in the Mongo Database).")
    raise SystemExit(0)

data = [{"choice": ch, "repo_url": repo}
        for repo in new_repos
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

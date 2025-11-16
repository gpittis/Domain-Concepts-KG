import sys
import os
import tempfile
import shutil
import zipfile
import urllib.request
from parsers.python_parser.python_parser import run_python_parser
from parsers.c_parser.c_lang_parser import run_c_parser
from parsers.cpp_parser.cpp_parser import run_cpp_parser
from parsers.java_parser.java_parser import run_java_parser
from parsers.javascript_parser.python_wrapper_for_js_parser import run_js_parser
from concept_filter.stopwords_filter import run_concept_filter
from structured_graph.json_creation_for_neo4j import run_kg_builder
from structured_graph.loader_script import run_neo4j_loader
from knowledge_graph.knowledge_graph_define_json import run_kg_builder_from_structured_graph
from knowledge_graph.update_knowledge_graph import run_knowledge_graph_loader
from structured_graph.delete_temporary_structured_graph import run_structured_graph_cleanup
from live_update_kg.graph_better_visualization import make_better_graph_visualization
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

# --- Available parser functions ---
# Each parser handles a different language
# CHOICES order matches LANGS by index 
# choice :
# "1" = cpp
# "2" = c
# "3" = python
# "4" = java
# "5" = javascript
CHOICES = [
    run_cpp_parser,     # index 0 → choice "1"
    run_c_parser,       # index 1 → choice "2"
    run_python_parser,  # index 2 → choice "3"
    run_java_parser,    # index 3 → choice "4"
    run_js_parser,      # index 4 → choice "5"
]

LANGS = ["cpp", "c_lang", "python", "java", "javascript"]

# --- GitHub helpers (download/unpack repos) ---
def _parse_github_tree(url: str):
    """
    Split GitHub URL of the form:
    https://github.com/owner/repo/tree/branch/subdir
    into (base_repo, branch, subdir).
    """
    if "github.com" in url and "/tree/" in url:
        before, after = url.split("/tree/", 1)
        parts = after.split("/", 1)
        return before, parts[0], (parts[1] if len(parts) > 1 else None)
    
    # If the URL does not contain "/tree/",
    # In that case, just return the original URL with branch=None and subdir=None.
    # So in that case, the function doesn’t run any logic, it simply passes the input back out.
    return url, None, None

def _owner_repo_from_base_repo_url(base_repo: str) -> tuple[str, str]:
    """
    Extract owner and repo from GitHub URL.
    Example: https://github.com/OWNER/REPO → ("OWNER", "REPO")
    """
    u = urlparse(base_repo) # break the URL into components
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2: # if there are fewer than two parts (meaning no OWNER or REPO)
        raise ValueError(f"Malformed GitHub repo URL: {base_repo}") # then i have error
    return parts[0], parts[1] # Returns the first part (the owner) and the second part (the repo name).

def _download_zip(url: str, out: Path): 
    """Download a zip file from URL to given output path."""
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[download] {url}")
    urllib.request.urlretrieve(url, out)

def _unzip(z: Path, to: Path) -> Path:
    to.mkdir(parents=True, exist_ok=True)
    print(f"[unzip] {z}")
    with zipfile.ZipFile(z, "r") as zf:
        target = str(to.resolve())
        if os.name == "nt" and not target.startswith(r"\\?\\"):
            target = r"\\?\\" + target   # σωστό prefix για long paths
        zf.extractall(target)
    entries = [p for p in to.iterdir()]
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else to


def _prepare_workspace_github(url: str) -> tuple[Path, Path]:
    
    """
    Return (local_codebase_dir, tmp_root).
    The caller (run_parser function) is responsible for cleaning up tmp_root afterwards.

    The function downloads the repository from GitHub as a .zip file, using the GitHub REST API.
    It then unzips that archive into a temporary folder on your computer.
    Finally, it returns the location (path) of the extracted codebase, 
    so the parser can read the source files from there.
    """

    # Create a temporary root directory for this workspace
    base_tmp = Path("C:/kg_ws")   # κοντή ρίζα αντί για AppData\Temp
    base_tmp.mkdir(parents=True, exist_ok=True)

    tmp_root = Path(tempfile.mkdtemp(prefix="kg_ws_", dir=base_tmp))

    # If the URL is already a direct .zip link, download and unzip it directly (ΔΕΝ ΤΟ ΔΟΚΙΜΑΣΑ)
    if url.lower().endswith(".zip"):
        zip_path = tmp_root / "repo.zip"
        _download_zip(url, zip_path)
        codebase = _unzip(zip_path, tmp_root / "unzipped")
        return codebase.resolve(), tmp_root

    # Otherwise: treat it as a normal GitHub repo URL
    # Split into (base_repo, branch/ref, subdir) if a tree path is included
    base_repo, ref, subdir = _parse_github_tree(url)
    owner, repo = _owner_repo_from_base_repo_url(base_repo)

    # Download zipball via GitHub REST API
    api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball" + (f"/{ref}" if ref else "")
    print(f"[zipball] GET {api_url}")

    # Send the HTTP GET request for the repo zipball
    req = urllib.request.Request(api_url, method="GET")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "kg-api-parser/1.0")

    # NEW: use token if provided
    token = os.getenv("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    # Download the response into a zip file inside the temporary folder
    zip_path = tmp_root / "repo.zip"
    with urllib.request.urlopen(req) as r, open(zip_path, "wb") as f:
        f.write(r.read())

    # Unzip the archive into tmp_root/unzipped
    repo_root = _unzip(zip_path, tmp_root / "unzipped")
    # adjust the path to point to that subdir inside the repo.
    codebase = (repo_root / subdir) if subdir else repo_root
    if subdir and not codebase.exists():
        raise RuntimeError(f"Subdir '{subdir}' not found in archive.")
    
    # Return the final codebase path and the root temp directory
    return codebase.resolve(), tmp_root

def run_parser(choice: str, repo_url: str) -> None:

    """
    Run the full pipeline for a selected language parser:
      1) Download and unpack repo
      2) Run language-specific parser
      3) Run concept filter
      4) Build Structured Graph JSON
      5) Load into Neo4j and create the temporary Structured Graph
      6) Build Knowledge Graph JSON from the temporary Structured Graph
      7) Create/update the final Knowledge Graph
      8) Cleanup the temporary structured-graph
      9) Graph Better Visualization
    Always cleans up temporary workspace.
    """

    # Convert choice string to index
    try:
        idx = int(choice) - 1
        parser_fn = CHOICES[idx]
        lang = LANGS[idx]
    except (ValueError, IndexError):
        raise KeyError("Invalid choice")

    # 1) Prepare local workspace (same helper as before)
    codebase, tmp_root = _prepare_workspace_github(repo_url)
    try:
        print(f"[run] {lang} parser")
        # 2) Run the language-specific parser
        main_json, comments_json = parser_fn(str(codebase))
        print(f"[parser-out] {lang}: out={main_json} comments={comments_json}")

        # Normalize to Path objects
        main_json_path = Path(main_json)
        # comments_json_path = Path(comments_json)

        if not main_json_path.exists():
            raise FileNotFoundError(f"Parser output not found: {main_json_path}")

        # 3) Concept filter 
        try:
            filtered_json = run_concept_filter(main_json_path)
            print(f"[done] concept filter -> {filtered_json}")
        except Exception as e:
            print(f"[warn] concept filter failed/skipped: {e}", file=sys.stderr)
            filtered_json = main_json_path 

        # 4) Build Structured Graph JSON 
        try:
            kg_json_path = run_kg_builder(Path(filtered_json))
            print(f"[done] KG JSON -> {kg_json_path}")
        except Exception as e:
            print(f"[warn] KG builder failed/skipped: {e}", file=sys.stderr)
            kg_json_path = None

        # 5) load the Structured Graph JSON into Neo4j and create the temporary Structured Graph
        try:
            if kg_json_path and Path(kg_json_path).exists():
                nodes, rels = run_neo4j_loader(Path(kg_json_path), repo_url=str(repo_url), database="structured-graph")
                print(
                    f"[neo4j-out] nodes={nodes} relationships={rels} ok=True")
            else:
                print("[warn] no KG JSON path; skipping Neo4j load.", file=sys.stderr)
        except Exception as e:
            print(f"[warn] Neo4j load failed/skipped: {e}", file=sys.stderr)

        # 6) Build knowledge_graph.json from the temporary Structured Graph
        try:
            base_dir = (kg_json_path.parent if kg_json_path else main_json_path.parent)
            kg_from_structured = base_dir / "knowledge_graph.json"

            kg_from_structured_path = run_kg_builder_from_structured_graph(
                output_path=str(kg_from_structured))
            print(f"[done] JSON : KNOWLEDGE GRAPH FROM STRUCTURED GRAPH -> {kg_from_structured_path}")
        except Exception as e:
            print(f"[warn] KG-from-structured build failed/skipped: {e}", file=sys.stderr)
            kg_from_structured_path = None

        # 7) Load the produced knowledge_graph.json into the final 'knowledge-graph' DB
        # Create/update the final Knowledge Graph
        try:
            if kg_from_structured_path and Path(kg_from_structured_path).exists():
                nodes_kg, rels_kg = run_knowledge_graph_loader(
                    input_json_path=str(kg_from_structured_path))
                print(f"[neo4j-kg] nodes={nodes_kg} relationships={rels_kg} ok=True")
            else:
                print("[warn] no knowledge_graph.json; skipping 'knowledge-graph' load.", file=sys.stderr)
        except Exception as e:
            print(f"[warn] knowledge-graph load failed/skipped: {e}", file=sys.stderr)
        
        # 8) Cleanup the temporary structured-graph
        try:
            run_structured_graph_cleanup()  # χρησιμοποιεί τα defaults
            print("[cleanup] structured-graph cleared.")
        except Exception as e:
            print(f"[warn] structured-graph cleanup failed: {e}", file=sys.stderr)

        # 9) Graph Better Visualization
        try:
            make_better_graph_visualization()
            print("[graph-visualization] completed")
        except Exception as e:
            print(f"[warn] graph-visualization failed: {e}", file=sys.stderr)

    finally:
        # Always clean tmp workspace
        shutil.rmtree(tmp_root, ignore_errors=True)

# --- FastAPI application (REST API implementation) ---
app = FastAPI(title="KG Parsers API", version="1.0")

# Schema for POST /parse requests
class ParseRequest(BaseModel):
    choice: str        # "1" (cpp), "2" (c), "3" (python), "4" (java), "5" (javascript)
    repo_url: HttpUrl  # GitHub URL

# Simple health check endpoint
@app.get("/health")
def health():
    return {"status": "ok"}

# Run parser pipeline for a given repo
@app.post("/parse")
def parse(req: ParseRequest):
    # Accept only GitHub hosts
    host = urlparse(str(req.repo_url)).netloc
    if "github.com" not in host and "codeload.github.com" not in host:
        raise HTTPException(status_code=400, detail="Only GitHub repo URLs are accepted.")

    try:
        run_parser(req.choice, str(req.repo_url))
        return {"status": "ok", "choice": req.choice}
    except SystemExit as e:
        raise HTTPException(status_code=500, detail=f"parser exited with code {e.code}")
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid choice")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


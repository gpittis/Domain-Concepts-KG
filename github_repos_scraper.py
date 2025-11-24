import requests
import json
import os
import sys
import subprocess
import time
from pathlib import Path

# ---------- Configuration ----------

STATE_FILE = "scraper_state.json"   # Stores current_page so we can resume across runs
OUTPUT_FILE = "repos.json"          # File consumed by automate_post_requests.py
DEFAULT_QUERY = "machine learning"  # Default search query if user presses Enter
RESULTS_PER_BATCH = 500             # How many repo URLs we want per scraping cycle
PER_PAGE = 100                      # GitHub Search API max per_page
SLEEP_SECONDS = 60  # π.χ. 1 ώρα == 3600 secs μεταξύ full passes

# Variants of the same base query
QUERY_VARIANTS = [
    "{base}",                 # plain base query
    "{base} stars:>100",      # with stars > 100
    "{base} forks:>500",      # with forks > 500
]

# ----------------------------------


def load_state():
    """
    Load scraper state for all queries from a JSON file.

    The state structure is a dict mapping:
        effective_query -> {"current_page": int}

    If the file does not exist or is invalid, return an empty dict.
    """
    p = Path(STATE_FILE)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # If the state file is broken, start with an empty state
        return {}


def save_state(state: dict) -> None:
    """
    Save scraper state for all queries to a JSON file.
    """
    Path(STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# Scraper function that automatically collects many GitHub repository URLs using the GitHub Search API.
def fetch_repo_links(query,
                     language="Python",
                     n_repos=RESULTS_PER_BATCH,
                     token=None,
                     sort="stars",
                     order="desc",
                     start_page=1):
    """
    Fetches multiple GitHub repository URLs automatically using the GitHub Search API,
    starting from a given page and scanning as many pages as needed until n_repos
    URLs are collected or there are no more results.

    Args:
        query (str): The search query string (e.g., "machine learning").
        language (str, optional): Programming language filter (e.g., "Python").
        n_repos (int, optional): Target number of repository URLs to collect.
        token (str, optional): GitHub personal access token for higher rate limits.
        sort (str, optional): Sorting field (e.g., "stars", "updated").
                              If None, GitHub uses "best match".
        order (str, optional): Sorting order, either "asc" or "desc". Default is "desc".
        start_page (int, optional): Page number to start scanning from.

    Returns:
        tuple[list[str], int]: A tuple (links, next_page) where:
            - links is the list of collected repository HTML URLs,
            - next_page is the page number from which the next run should continue.
    """

    base_url = "https://api.github.com/search/repositories"  # GitHub Search API endpoint
    per_page = PER_PAGE                                     # GitHub API maximum allowed items per page

    # Request headers sent to GitHub API
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    all_links = []  # This list will store all extracted repository URLs
    page = start_page

    # Keep fetching pages until we collect n_repos or there are no more results
    while len(all_links) < n_repos:
        # Build query parameters for GitHub API request
        params = {
            "q": f"{query} language:{language}" if language else query,
            "per_page": per_page,
            "page": page,
        }

        # Apply sorting only if explicitly requested
        if sort is not None:
            params["sort"] = sort
            params["order"] = order

        print(f"[INFO] Fetching page {page}...", file=sys.stderr)

        # Send GET request to GitHub API
        resp = requests.get(base_url, headers=headers, params=params)

        # Stop execution if GitHub returned an error
        if resp.status_code != 200:
            print(f"[ERROR] GitHub API returned {resp.status_code}: {resp.text}", file=sys.stderr)
            break

        data = resp.json()
        items = data.get("items", [])

        # If there are no items, we have reached the end of the search results
        if not items:
            print("[INFO] No more items returned by API.", file=sys.stderr)
            break

        # Extract repository URLs from the current page
        for item in items:
            url = item.get("html_url")
            if url:
                all_links.append(url)
                if len(all_links) >= n_repos:
                    break

        # Move to the next page for the next iteration
        page += 1

    print(f"[INFO] Collected {len(all_links)} links (requested {n_repos}).", file=sys.stderr)

    # Return the collected links and the next page number to continue from
    return all_links, page


def run_one_full_pass(user_query: str, token: str | None) -> None:
    """
    Εκτελεί ΕΝΑ πλήρες πέρασμα πάνω από όλα τα query variants.
    Δεν ρωτάει τον χρήστη, ούτε ξαναδιαβάζει το token.
    Χρησιμοποιεί και ενημερώνει το per-query state.
    """
    # Build the 3 query variants
    queries = [tpl.format(base=user_query) for tpl in QUERY_VARIANTS]

    # Load global state (per-query pages)
    state = load_state()

    # Process each query variant separately, with its own page state
    for effective_query in queries:
        # Get current_page for this specific query (default to 1)
        q_state = state.get(effective_query, {})
        current_page = q_state.get("current_page", 1)

        print(f"[INFO] === Processing query: {effective_query!r} (starting from page {current_page}) ===", file=sys.stderr)

        while True:
            print(f"[INFO] Starting new scraping cycle from page {current_page} for query {effective_query!r}...", file=sys.stderr)

            # Fetch repository URLs for the given query and programming language.
            links, next_page = fetch_repo_links(
                query=effective_query,
                language="Python",
                n_repos=RESULTS_PER_BATCH,
                token=token,
                sort=None,     # None -> GitHub "best match" for each query variant
                start_page=current_page,
            )

            # If no links were retrieved, there is nothing more to do for this query.
            if not links:
                print(f"[INFO] No more repositories found for query: {effective_query!r}. Moving to next query.", file=sys.stderr)
                break

            # Write the repository URLs to a JSON ARRAY file.
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                # Dump the list of links as a JSON array with pretty formatting
                json.dump(links, f, indent=2, ensure_ascii=False)

            print(f"[INFO] Saved {len(links)} links to {OUTPUT_FILE} for query {effective_query!r}", file=sys.stderr)

            # Run the second script that processes repos.json.
            # This call BLOCKS until automate_post_requests.py finishes all POST requests.
            try:
                subprocess.run(
                    [sys.executable, "automate_post_requests.py"],
                    check=True
                )
                print("[INFO] Successfully ran automate_post_requests.py", file=sys.stderr)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] automate_post_requests.py failed: {e}", file=sys.stderr)
                # You may choose to break here or continue with next query.
                break

            # Update current_page for THIS query and persist it
            current_page = next_page
            state[effective_query] = {"current_page": current_page}
            save_state(state)
            print(f"[INFO] Updated state for query {effective_query!r}: next start_page = {current_page}", file=sys.stderr)

            # Optional: sleep between pages if you want to throttle things a bit.
            # time.sleep(600)

    print("[INFO] All query variants completed for this pass.", file=sys.stderr)

    # Στο τέλος ενός FULL pass, reset-άρουμε τα pages όλων των queries σε 1,
    # ώστε στο επόμενο pass να ξανασκανάρουμε από την αρχή (page 1).
    state = load_state()
    for effective_query in queries:
        state[effective_query] = {"current_page": 1}
    save_state(state)
    print("[INFO] Reset current_page=1 for all query variants (ready for next pass).", file=sys.stderr)


def main():
    """
    Infinite loop:
    - Reads token and base query once.
    - Then forever:
        * runs one full pass over all query variants
        * sleeps for SLEEP_SECONDS
        * repeats
    """
    # Read GitHub personal access token from environment variable.
    token = os.getenv("GITHUB_TOKEN")

    # Warn the user if no token is provided (unauthenticated requests have low rate limits).
    if token is None:
        print("[WARN] No GitHub token provided. You may hit rate limits.", file=sys.stderr)

    # Ask the user for the base search query (domain name / topic).
    user_query = input("Enter GitHub search query : ").strip()
    if not user_query:
        user_query = DEFAULT_QUERY

    # Endless loop: keep repeating the full pass + sleep
    while True:
        print("[INFO] ===== Starting new FULL PASS over all query variants =====", file=sys.stderr)
        run_one_full_pass(user_query, token)
        print(f"[INFO] FULL PASS finished. Sleeping for {SLEEP_SECONDS} seconds before restarting...", file=sys.stderr)
        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()

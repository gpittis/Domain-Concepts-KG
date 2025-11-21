import requests
import json
import math
import os
import sys
import subprocess

# Scraper function that automatically collects many GitHub repository URLs using the GitHub Search API.
def fetch_repo_links(query, language="Python", n_repos=500, token=None, sort=None, order="desc"):

    """
    Fetches multiple GitHub repository URLs automatically using the GitHub Search API.

    Args:
        query (str): The search query string (e.g., "machine learning").
        language (str, optional): Programming language filter (e.g., "Python").
        n_repos (int, optional): Maximum number of repository URLs to retrieve.
        token (str, optional): GitHub personal access token for higher rate limits.
        sort (str, optional): Sorting field (e.g., "stars"). If None, GitHub uses "best match".
        order (str, optional): Sorting order, either "asc" or "desc". Default is "desc".

    Returns:
        list[str]: A list containing GitHub repository HTML URLs.
    """

    base_url = "https://api.github.com/search/repositories" # Endpoint of GitHub Search API (for repos)
    per_page = 100  # GitHub API maximum allowed items per page
    max_pages = math.ceil(n_repos / per_page) # Number of API pages required
    # If i want 500 repo urls : max_pages = 500/100 = 5 pages.

    # Request headers sent to GitHub API
    headers = {
        "Accept": "application/vnd.github+json"
    }
    # Add authorization header if a token is provided
    if token:
        headers["Authorization"] = f"Bearer {token}"

    all_links = [] # This list will store all extracted repository URLs

    # Loop through all pages required to collect n_repos (e.g. 500 repos) results
    for page in range(1, max_pages + 1):
        
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

        # Stop if GitHub returns no more results
        if not items:
            print("[INFO] No more items returned by API.", file=sys.stderr)
            break
        
        # Extract repository URLs from the current page
        for item in items:
            url = item.get("html_url")
            if url:
                all_links.append(url)

                # Stop early if we already collected enough URLs
                if len(all_links) >= n_repos:
                    break
        
        # Break the outer loop as well if enough results have been collected
        if len(all_links) >= n_repos:
            break
    
    # Return only the first n_repos items. 
    # This acts as a safety check in case future changes accidentally append more items than requested.
    # (For now, the :n_repos slicing is optional).
    return all_links[:n_repos]


def main():

    # Read GitHub personal access token from environment variable.
    token = os.getenv("GITHUB_TOKEN")

    # Warn the user if no token is provided (unauthenticated requests have low rate limits).
    if token is None:
        print("[WARN] No GitHub token provided. You may hit rate limits.", file=sys.stderr)

    # Ask the user for the search query (domain name / topic).
    # Pressing Enter with no input will fall back to the default "machine learning".
    user_query = input("Enter GitHub search query : ").strip()
    if not user_query:
        user_query = "machine learning"

    # Fetch repository URLs for the given query (i.e. domain name) and programming language.
    links = fetch_repo_links(
        query=user_query,
        language="Python",
        n_repos=500,
        token=token
    )

   # Write the repository URLs to a JSON ARRAY file.
    output_file = "repos.json"
    with open(output_file, "w", encoding="utf-8") as f:
        # Dump the list of links as a JSON array with pretty formatting
        json.dump(links, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Saved {len(links)} links to {output_file}", file=sys.stderr)

    # Now call the second script that processes repos.json
    try:
        subprocess.run(
            [sys.executable, "automate_post_requests.py"],
            check=True
        )
        print("[INFO] Successfully ran automate_post_requests.py", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] automate_post_requests.py failed: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()

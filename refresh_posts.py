#!/usr/bin/env python3
"""
Run this locally whenever you publish new Substack articles.
It fetches your posts and saves them to posts_cache.json so
GitHub Actions can read them without hitting the Substack API.

Usage: python refresh_posts.py
"""

import re
import json
import requests
from pathlib import Path

SUBDOMAIN = "sproutingplant"
CACHE_FILE = Path(__file__).parent / "posts_cache.json"

def fetch_all_posts():
    posts = []
    for offset in range(0, 100, 10):
        r = requests.get(
            f"https://{SUBDOMAIN}.substack.com/api/v1/posts",
            params={"limit": 10, "offset": offset},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            timeout=15,
        )
        if not r.ok:
            break
        batch = r.json().get("posts", r.json()) if isinstance(r.json(), dict) else r.json()
        if not batch:
            break
        posts.extend(batch)
        if len(batch) < 10:
            break
    return posts

def main():
    print("Fetching posts from Substack...")
    raw = fetch_all_posts()
    cache = []
    for p in raw:
        body_html = p.get("body_html", "") or ""
        body_text = re.sub(r"<[^>]+>", " ", body_html)
        body_text = re.sub(r"\s+", " ", body_text).strip()
        cache.append({
            "slug": p["slug"],
            "title": p.get("title", ""),
            "subtitle": p.get("subtitle", ""),
            "body": body_text[:4000],
        })
    CACHE_FILE.write_text(json.dumps(cache, indent=2))
    print(f"Saved {len(cache)} posts to posts_cache.json")
    for p in cache:
        print(f"  - {p['slug']}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Post a generated carousel as a photo album to the AI and Spirituality Facebook Page.
Usage: python post_to_facebook.py <slug> "<caption text>"
"""

import os
import sys
import time
import subprocess
import shutil
from pathlib import Path

import requests

GRAPH_BASE = "https://graph.facebook.com/v21.0"
PAGE_ID = "1235072103015320"

GITHUB_REPO = "https://github.com/FlorenceMawusi/carousel-assets"
GITHUB_RAW = "https://raw.githubusercontent.com/FlorenceMawusi/carousel-assets/main"
ASSETS_DIR = Path(__file__).parent / "carousel-assets-repo"


def ensure_assets_repo():
    if not ASSETS_DIR.exists():
        subprocess.run(["git", "clone", GITHUB_REPO, str(ASSETS_DIR)], check=True)
    else:
        subprocess.run(["git", "-C", str(ASSETS_DIR), "pull"], check=True)


def get_github_urls(slides: list[Path], slug: str) -> list[str]:
    """Push slides to GitHub if not already there, return raw URLs."""
    ensure_assets_repo()
    dest = ASSETS_DIR / slug
    dest.mkdir(parents=True, exist_ok=True)

    pushed = False
    for slide in slides:
        target = dest / slide.name
        if not target.exists():
            shutil.copy(slide, target)
            pushed = True

    if pushed:
        subprocess.run(["git", "-C", str(ASSETS_DIR), "add", "."], check=True)
        subprocess.run(["git", "-C", str(ASSETS_DIR), "commit", "-m", f"add carousel: {slug}"], check=True)
        subprocess.run(["git", "-C", str(ASSETS_DIR), "push"], check=True)
        print("  Pushed images to GitHub. Waiting for CDN propagation ...")
        time.sleep(5)
    else:
        print("  Images already on GitHub, reusing existing URLs.")

    return [f"{GITHUB_RAW}/{slug}/{slide.name}" for slide in slides]


def upload_photo_unpublished(token: str, image_url: str) -> str:
    """Upload a photo to the page without publishing it; returns photo ID."""
    resp = requests.post(
        f"{GRAPH_BASE}/{PAGE_ID}/photos",
        data={
            "url": image_url,
            "published": "false",
            "access_token": token,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Photo upload error: {resp.text}")
    resp.raise_for_status()
    return resp.json()["id"]


def publish_multi_photo_post(token: str, photo_ids: list[str], caption: str) -> dict:
    """Publish a multi-photo post using the uploaded photo IDs."""
    attached = [{"media_fbid": pid} for pid in photo_ids]
    resp = requests.post(
        f"{GRAPH_BASE}/{PAGE_ID}/feed",
        json={
            "message": caption,
            "attached_media": attached,
            "access_token": token,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Publish error: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 3:
        print('Usage: python post_to_facebook.py <slug> "<caption>"')
        sys.exit(1)

    slug = sys.argv[1]
    caption = sys.argv[2]

    token = os.environ.get("FB_PAGE_TOKEN")
    if not token:
        print("Error: FB_PAGE_TOKEN must be set.")
        sys.exit(1)

    slide_dir = Path("output") / slug
    slides = sorted(slide_dir.glob("slide_*.png"))
    if not slides:
        print(f"No slides found in {slide_dir}")
        sys.exit(1)

    print(f"Found {len(slides)} slides.")
    image_urls = get_github_urls(slides, slug)
    for url in image_urls:
        print(f"  ✓ {url}")

    print("\nUploading photos to Facebook (unpublished) ...")
    photo_ids = []
    for url in image_urls:
        pid = upload_photo_unpublished(token, url)
        photo_ids.append(pid)
        print(f"  ✓ photo {pid}")
        time.sleep(1)

    print("\nPublishing multi-photo post to AI and Spirituality Page ...")
    result = publish_multi_photo_post(token, photo_ids, caption)
    print(f"\nDone! Post ID: {result}")


if __name__ == "__main__":
    main()

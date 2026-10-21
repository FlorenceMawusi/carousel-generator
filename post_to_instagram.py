#!/usr/bin/env python3
"""
Post a generated carousel to Instagram.
Usage: python post_to_instagram.py <slug> "<caption text>"
"""

import os
import sys
import time
from pathlib import Path

import requests

GRAPH_BASE = "https://graph.instagram.com/v21.0"


GITHUB_REPO = "https://github.com/FlorenceMawusi/carousel-assets"
GITHUB_RAW = "https://raw.githubusercontent.com/FlorenceMawusi/carousel-assets/main"
ASSETS_DIR = Path(__file__).parent / "carousel-assets-repo"


def ensure_assets_repo():
    """Clone the assets repo if not already present, otherwise pull latest."""
    import subprocess
    if not ASSETS_DIR.exists():
        subprocess.run(["git", "clone", GITHUB_REPO, str(ASSETS_DIR)], check=True)
    else:
        subprocess.run(["git", "-C", str(ASSETS_DIR), "pull"], check=True)


def upload_slides_to_github(slides: list[Path], slug: str) -> list[str]:
    import subprocess, shutil
    ensure_assets_repo()

    dest = ASSETS_DIR / slug
    dest.mkdir(parents=True, exist_ok=True)
    for slide in slides:
        shutil.copy(slide, dest / slide.name)

    subprocess.run(["git", "-C", str(ASSETS_DIR), "add", "."], check=True)
    result = subprocess.run(
        ["git", "-C", str(ASSETS_DIR), "commit", "-m", f"add carousel: {slug}"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        subprocess.run(["git", "-C", str(ASSETS_DIR), "push"], check=True)
    else:
        print("  Images already on GitHub, reusing existing URLs.")

    return [f"{GITHUB_RAW}/{slug}/{slide.name}" for slide in slides]


def create_carousel_item(user_id: str, token: str, image_url: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{user_id}/media",
        data={
            "image_url": image_url,
            "is_carousel_item": "true",
            "access_token": token,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Error creating carousel item: {resp.text}")
    resp.raise_for_status()
    return resp.json()["id"]


def create_carousel_container(user_id: str, token: str, children: list, caption: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{user_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
            "access_token": token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def publish_container(user_id: str, token: str, creation_id: str) -> dict:
    resp = requests.post(
        f"{GRAPH_BASE}/{user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    if len(sys.argv) < 3:
        print('Usage: python post_to_instagram.py <slug> "<caption text>"')
        sys.exit(1)

    slug = sys.argv[1]
    caption = sys.argv[2]

    token = os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    if not token or not user_id:
        print("Error: IG_ACCESS_TOKEN and IG_USER_ID must be set.")
        sys.exit(1)

    slide_dir = Path("output") / slug
    slides = sorted(slide_dir.glob("slide_*.png"))
    if not slides:
        print(f"No slides found in {slide_dir}")
        sys.exit(1)

    print(f"Found {len(slides)} slides. Pushing to GitHub ...")
    image_urls = upload_slides_to_github(slides, slug)
    for url in image_urls:
        print(f"  ✓ {url}")
    print("\nWaiting for GitHub CDN to propagate ...")
    time.sleep(5)

    print("\nCreating Instagram media containers ...")
    children = []
    for url in image_urls:
        item_id = create_carousel_item(user_id, token, url)
        children.append(item_id)
        print(f"  ✓ container {item_id}")
        time.sleep(1)  # avoid rate-limit bursts

    print("\nCreating carousel container ...")
    creation_id = create_carousel_container(user_id, token, children, caption)
    print(f"  ✓ creation_id {creation_id}")

    print("\nWaiting a few seconds for Instagram to process media ...")
    time.sleep(8)

    print("Publishing carousel ...")
    result = publish_container(user_id, token, creation_id)
    print(f"\nDone! Published post: {result}")


if __name__ == "__main__":
    main()

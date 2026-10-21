#!/usr/bin/env python3
"""
Full carousel pipeline: fetch latest Substack article → generate slides →
auto-generate caption → post to Instagram + Facebook.

Tracks which articles have already been posted in posted.json to avoid duplicates.
"""

import os
import re
import json
import time
import base64
import subprocess
import shutil
import random
import logging
from pathlib import Path
from io import BytesIO

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

LOG_FILE = Path(__file__).parent / "pipeline.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────
SUBDOMAIN = "sproutingplant"
IG_GRAPH = "https://graph.instagram.com/v21.0"
FB_GRAPH = "https://graph.facebook.com/v21.0"
FB_PAGE_ID = "1235072103015320"
IG_USER_ID = "27387358564207576"

GITHUB_REPO = "https://github.com/FlorenceMawusi/carousel-assets"
GITHUB_RAW = "https://raw.githubusercontent.com/FlorenceMawusi/carousel-assets/main"
ASSETS_DIR = Path(__file__).parent / "carousel-assets-repo"
OUTPUT_DIR = Path(__file__).parent / "output"
POSTED_LOG = Path(__file__).parent / "posted.json"

# ── Brand ──────────────────────────────────────────────────────────────────────
BRAND = {
    "bg": (26, 16, 8), "accent": (232, 68, 10), "gold": (200, 134, 10),
    "text": (245, 240, 232), "card": (45, 31, 14),
    "handle": "@sproutingplant",
}
SIZE = 1024
BG_STYLE_PROMPT = (
    "Abstract editorial background art. Dark warm tones, deep brown-black (#1A1008), "
    "subtle red-orange (#E8440A) and gold (#C8860A) light streaks or textures. "
    "No text, no words, no letters, no numbers. "
    "Cinematic, moody, minimal. Square 1:1 format."
)


# ── Helpers ────────────────────────────────────────────────────────────────────
def load_fonts():
    candidates_bold = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    candidates_regular = [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    def try_load(paths, size):
        for p in paths:
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        return ImageFont.load_default()
    return {
        "headline": try_load(candidates_bold, 72),
        "headline_sm": try_load(candidates_bold, 58),
        "body": try_load(candidates_regular, 36),
        "handle": try_load(candidates_regular, 28),
    }


def load_posted() -> set:
    if POSTED_LOG.exists():
        return set(json.loads(POSTED_LOG.read_text()))
    return set()


def save_posted(posted: set):
    POSTED_LOG.write_text(json.dumps(sorted(posted), indent=2))


# ── Substack ───────────────────────────────────────────────────────────────────
def fetch_random_unposted() -> dict | None:
    posted = load_posted()
    # fetch up to 50 posts to build a good pool
    all_posts = []
    for offset in range(0, 50, 10):
        r = requests.get(
            f"https://{SUBDOMAIN}.substack.com/api/v1/posts",
            params={"limit": 10, "offset": offset},
            timeout=15,
        )
        if not r.ok:
            break
        batch = r.json().get("posts", r.json()) if isinstance(r.json(), dict) else r.json()
        if not batch:
            break
        all_posts.extend(batch)

    unposted = [p for p in all_posts if p.get("slug") and p["slug"] not in posted]
    if not unposted:
        return None

    post = random.choice(unposted)
    body_html = post.get("body_html", "") or ""
    body_text = re.sub(r"<[^>]+>", " ", body_html)
    body_text = re.sub(r"\s+", " ", body_text).strip()
    return {
        "slug": post["slug"],
        "title": post.get("title", ""),
        "subtitle": post.get("subtitle", ""),
        "body": body_text[:4000],
    }


# ── Slide generation ───────────────────────────────────────────────────────────
def generate_slide_scripts(client: OpenAI, article: dict) -> list[dict]:
    system = (
        "You are a social media content strategist. "
        "Given an article, produce a 6-slide Instagram/Facebook carousel script. "
        'Return a JSON object with a single key "slides" whose value is an array of exactly 6 objects. '
        'Each object must have: "slide" (int 1-6), "headline" (max 7 words, punchy, no punctuation except ?), '
        '"body" (max 18 words), '
        '"visual_direction" (1 sentence: abstract visual concept, no text, no faces, no people). '
        "Slide 1 = cover hook. Slides 2-5 = key insights. Slide 6 = CTA to read full article."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Title: {article['title']}\nSubtitle: {article['subtitle']}\n\n{article['body']}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    parsed = json.loads(resp.choices[0].message.content)
    if isinstance(parsed, list):
        return parsed
    for val in parsed.values():
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
            return val
    raise ValueError("Unexpected GPT-4o response shape")


def generate_caption(client: OpenAI, article: dict) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": (
                f"Write an Instagram/Facebook caption for this article. "
                f"Plain English, no em dashes, conversational tone, 3-5 sentences max. "
                f"End with 'Full essay, link in bio' and 4-5 relevant hashtags.\n\n"
                f"Title: {article['title']}\nSubtitle: {article['subtitle']}\n\n{article['body'][:1500]}"
            )
        }],
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()


def draw_wrapped_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if draw.textbbox((0, 0), test, font=font)[2] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def composite_text(bg: Image.Image, slide: dict, fonts: dict, slide_num: int, total: int) -> Image.Image:
    img = bg.copy()
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    gradient_top = int(SIZE * 0.32)
    for y in range(gradient_top, SIZE):
        alpha = int(220 * (y - gradient_top) / (SIZE - gradient_top))
        ov_draw.line([(0, y), (SIZE, y)], fill=(26, 16, 8, alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img, "RGBA")

    pad, max_w = 60, SIZE - 120
    accent, gold, text_color = BRAND["accent"], BRAND["gold"], BRAND["text"]

    dot_r, dot_spacing = 5, 18
    total_dot_w = total * dot_spacing - (dot_spacing - dot_r * 2)
    dot_x = (SIZE - total_dot_w) // 2
    dot_y = SIZE - 36
    for i in range(total):
        color = accent if i == slide_num - 1 else (100, 80, 60, 180)
        draw.ellipse([dot_x, dot_y, dot_x + dot_r * 2, dot_y + dot_r * 2], fill=color)
        dot_x += dot_spacing

    handle_bbox = draw.textbbox((0, 0), BRAND["handle"], font=fonts["handle"])
    draw.text(((SIZE - (handle_bbox[2] - handle_bbox[0])) // 2, SIZE - 68),
              BRAND["handle"], font=fonts["handle"], fill=gold)

    bar_y = int(SIZE * 0.42)
    draw.rectangle([pad, bar_y, pad + 48, bar_y + 6], fill=accent)

    headline = slide["headline"].upper()
    font = fonts["headline"] if len(headline) < 30 else fonts["headline_sm"]
    lines = draw_wrapped_text(draw, headline, font, max_w)
    y = bar_y + 22
    for line in lines:
        draw.text((pad, y), line, font=font, fill=text_color)
        y += font.size + 10

    body_y = y + 18
    for line in draw_wrapped_text(draw, slide["body"], fonts["body"], max_w):
        draw.text((pad, body_y), line, font=fonts["body"], fill=(220, 210, 195))
        body_y += fonts["body"].size + 8

    return img.convert("RGB")


def generate_slides(client: OpenAI, article: dict) -> list[Path]:
    slides = generate_slide_scripts(client, article)
    out_dir = OUTPUT_DIR / article["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()
    total = len(slides)
    saved = []
    for slide in slides:
        n = slide["slide"]
        print(f"  Generating slide {n}/{total} ...")
        prompt = f"{BG_STYLE_PROMPT} Concept: {slide['visual_direction']}"
        resp = client.images.generate(model="gpt-image-1", prompt=prompt, size="1024x1024", quality="medium", n=1)
        bg = Image.open(BytesIO(base64.b64decode(resp.data[0].b64_json))).convert("RGBA")
        final = composite_text(bg, slide, fonts, n, total)
        path = out_dir / f"slide_{n:02d}.png"
        final.save(path, "PNG")
        saved.append(path)
    return saved


# ── GitHub hosting ─────────────────────────────────────────────────────────────
def push_to_github(slides: list[Path], slug: str) -> list[str]:
    if not ASSETS_DIR.exists():
        subprocess.run(["git", "clone", GITHUB_REPO, str(ASSETS_DIR)], check=True)
    else:
        subprocess.run(["git", "-C", str(ASSETS_DIR), "pull"], check=True)

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

    return [f"{GITHUB_RAW}/{slug}/{s.name}" for s in slides]


# ── Instagram posting ──────────────────────────────────────────────────────────
def post_to_instagram(image_urls: list[str], caption: str):
    token = os.environ["IG_ACCESS_TOKEN"]
    children = []
    for url in image_urls:
        resp = requests.post(f"{IG_GRAPH}/{IG_USER_ID}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": token}, timeout=30)
        if not resp.ok:
            print(f"  IG item error: {resp.text}")
        resp.raise_for_status()
        children.append(resp.json()["id"])
        time.sleep(1)

    resp = requests.post(f"{IG_GRAPH}/{IG_USER_ID}/media",
        data={"media_type": "CAROUSEL", "children": ",".join(children),
              "caption": caption, "access_token": token}, timeout=30)
    resp.raise_for_status()
    creation_id = resp.json()["id"]
    time.sleep(8)

    resp = requests.post(f"{IG_GRAPH}/{IG_USER_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": token}, timeout=30)
    resp.raise_for_status()
    print(f"  ✓ Instagram: {resp.json()}")


# ── Facebook posting ───────────────────────────────────────────────────────────
def post_to_facebook(image_urls: list[str], caption: str):
    token = os.environ["FB_PAGE_TOKEN"]
    photo_ids = []
    for url in image_urls:
        resp = requests.post(f"{FB_GRAPH}/{FB_PAGE_ID}/photos",
            data={"url": url, "published": "false", "access_token": token}, timeout=30)
        if not resp.ok:
            print(f"  FB photo error: {resp.text}")
        resp.raise_for_status()
        photo_ids.append(resp.json()["id"])
        time.sleep(1)

    resp = requests.post(f"{FB_GRAPH}/{FB_PAGE_ID}/feed",
        json={"message": caption, "attached_media": [{"media_fbid": pid} for pid in photo_ids],
              "access_token": token}, timeout=30)
    if not resp.ok:
        print(f"  FB publish error: {resp.text}")
    resp.raise_for_status()
    print(f"  ✓ Facebook: {resp.json()}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.error("OPENAI_API_KEY not set.")
        return
    if not os.environ.get("IG_ACCESS_TOKEN") or not os.environ.get("FB_PAGE_TOKEN"):
        log.error("IG_ACCESS_TOKEN and FB_PAGE_TOKEN must be set.")
        return

    client = OpenAI(api_key=api_key)

    log.info("Picking a random unposted Substack article ...")
    article = fetch_random_unposted()
    if not article:
        log.info("No new articles to post. All caught up!")
        return

    log.info(f"Found new article: {article['title']} ({article['slug']})")

    log.info("Generating carousel slides ...")
    slides = generate_slides(client, article)
    log.info(f"Generated {len(slides)} slides.")

    log.info("Generating caption ...")
    caption = generate_caption(client, article)
    log.info(f"Caption: {caption}")

    log.info("Pushing images to GitHub ...")
    image_urls = push_to_github(slides, article["slug"])
    log.info(f"Pushed {len(image_urls)} images.")
    time.sleep(5)

    log.info("Posting to Instagram ...")
    post_to_instagram(image_urls, caption)

    log.info("Posting to Facebook ...")
    post_to_facebook(image_urls, caption)

    posted = load_posted()
    posted.add(article["slug"])
    save_posted(posted)

    log.info(f"Done! '{article['title']}' posted to Instagram and Facebook.")


if __name__ == "__main__":
    main()

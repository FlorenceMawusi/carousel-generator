#!/usr/bin/env python3
"""
Carousel Generator — Florence / AI and Humans
Fetches a Substack article, generates 6 branded carousel slides using GPT-4o + gpt-image-1.
Text is composited with Pillow for crisp, typo-free rendering.
"""

import os
import sys
import json
import re
import base64
import textwrap
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

# ── Brand ──────────────────────────────────────────────────────────────────────
BRAND = {
    "bg":          (26, 16, 8),      # #1A1008
    "accent":      (232, 68, 10),    # #E8440A
    "gold":        (200, 134, 10),   # #C8860A
    "text":        (245, 240, 232),  # #F5F0E8
    "card":        (45, 31, 14),     # #2D1F0E
    "overlay":     (26, 16, 8, 200), # semi-transparent dark
    "handle":      "@sproutingplant",
    "subdomain":   "sproutingplant.substack.com",
}

SIZE = 1024  # square slide

BG_STYLE_PROMPT = (
    "Abstract editorial background art. Dark warm tones, deep brown-black (#1A1008), "
    "subtle red-orange (#E8440A) and gold (#C8860A) light streaks or textures. "
    "No text, no words, no letters, no numbers. "
    "Cinematic, moody, minimal. Square 1:1 format."
)

# ── Font loading ───────────────────────────────────────────────────────────────
def load_fonts():
    """Try to load system fonts; fall back to PIL default."""
    candidates_bold = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    candidates_regular = [
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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
        "slide_num": try_load(candidates_bold, 24),
    }


# ── Article fetching ───────────────────────────────────────────────────────────
def fetch_article(subdomain: str, slug: str) -> dict:
    url = f"https://{subdomain}.substack.com/api/v1/posts/{slug}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    body_html = data.get("body_html", "") or ""
    body_text = re.sub(r"<[^>]+>", " ", body_html)
    body_text = re.sub(r"\s+", " ", body_text).strip()
    return {
        "title": data.get("title", ""),
        "subtitle": data.get("subtitle", ""),
        "body": body_text[:4000],
    }


# ── Slide script generation ────────────────────────────────────────────────────
def generate_slide_scripts(client: OpenAI, article: dict) -> list[dict]:
    system = (
        "You are a social media content strategist. "
        "Given an article, produce a 6-slide Instagram/Facebook carousel script. "
        'Return a JSON object with a single key "slides" whose value is an array of exactly 6 objects. '
        'Each object must have: "slide" (int 1-6), "headline" (max 7 words, punchy, no punctuation except ?), '
        '"body" (max 18 words, insight or elaboration), '
        '"visual_direction" (1 sentence: abstract visual concept, no text, no faces, no people). '
        "Slide 1 = cover hook. Slides 2-5 = key insights. Slide 6 = CTA to read full article."
    )
    user = (
        f"Title: {article['title']}\n"
        f"Subtitle: {article['subtitle']}\n\n"
        f"Article:\n{article['body']}"
    )
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    parsed = json.loads(response.choices[0].message.content)
    if isinstance(parsed, list):
        return parsed
    for val in parsed.values():
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
            return val
    raise ValueError(f"Unexpected GPT-4o response shape: {list(parsed.keys())}")


# ── Background image generation ────────────────────────────────────────────────
def generate_background(client: OpenAI, visual_direction: str) -> Image.Image:
    prompt = f"{BG_STYLE_PROMPT} Concept: {visual_direction}"
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="medium",
        n=1,
    )
    img_bytes = base64.b64decode(response.data[0].b64_json)
    return Image.open(BytesIO(img_bytes)).convert("RGBA")


# ── Text compositing ───────────────────────────────────────────────────────────
def draw_wrapped_text(draw, text, font, max_width, color):
    """Wrap text to fit max_width, return lines."""
    words = text.split()
    lines = []
    current = []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def composite_text(bg: Image.Image, slide: dict, fonts: dict, slide_num: int, total: int) -> Image.Image:
    img = bg.copy()
    draw = ImageDraw.Draw(img, "RGBA")

    pad = 60
    max_w = SIZE - pad * 2
    text_color = BRAND["text"]
    accent = BRAND["accent"]
    gold = BRAND["gold"]

    # ── Dark gradient overlay (bottom 55%) ─────────────────────────────────────
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    gradient_top = int(SIZE * 0.32)
    for y in range(gradient_top, SIZE):
        alpha = int(220 * (y - gradient_top) / (SIZE - gradient_top))
        ov_draw.line([(0, y), (SIZE, y)], fill=(26, 16, 8, alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img, "RGBA")

    # ── Slide number dots ──────────────────────────────────────────────────────
    dot_r = 5
    dot_spacing = 18
    total_dot_w = total * dot_spacing - (dot_spacing - dot_r * 2)
    dot_x = (SIZE - total_dot_w) // 2
    dot_y = SIZE - 36
    for i in range(total):
        color = accent if i == slide_num - 1 else (100, 80, 60, 180)
        draw.ellipse([dot_x, dot_y, dot_x + dot_r * 2, dot_y + dot_r * 2], fill=color)
        dot_x += dot_spacing

    # ── Handle ────────────────────────────────────────────────────────────────
    handle_bbox = draw.textbbox((0, 0), BRAND["handle"], font=fonts["handle"])
    handle_w = handle_bbox[2] - handle_bbox[0]
    draw.text(((SIZE - handle_w) // 2, SIZE - 68), BRAND["handle"],
              font=fonts["handle"], fill=gold)

    # ── Accent bar ────────────────────────────────────────────────────────────
    bar_y = int(SIZE * 0.42)
    draw.rectangle([pad, bar_y, pad + 48, bar_y + 6], fill=accent)

    # ── Headline ──────────────────────────────────────────────────────────────
    headline = slide["headline"].upper()
    font = fonts["headline"] if len(headline) < 30 else fonts["headline_sm"]
    lines = draw_wrapped_text(draw, headline, font, max_w, text_color)

    line_h = font.size + 10
    total_h = len(lines) * line_h
    y = bar_y + 22

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text((pad, y), line, font=font, fill=text_color)
        y += line_h

    # ── Body text ─────────────────────────────────────────────────────────────
    body_y = y + 18
    body_lines = draw_wrapped_text(draw, slide["body"], fonts["body"], max_w, text_color)
    for line in body_lines:
        draw.text((pad, body_y), line, font=fonts["body"], fill=(220, 210, 195))
        body_y += fonts["body"].size + 8

    return img.convert("RGB")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_carousel.py <substack-url-or-slug>")
        print("Example: python generate_carousel.py understanding-the-kaparthy-loop")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    arg = sys.argv[1].rstrip("/")
    if "substack.com" in arg:
        match = re.search(r"substack\.com/p/([^/?]+)", arg)
        slug = match.group(1) if match else arg.split("/")[-1]
        subdomain_match = re.search(r"https?://([^.]+)\.substack\.com", arg)
        subdomain = subdomain_match.group(1) if subdomain_match else "sproutingplant"
    else:
        slug = arg
        subdomain = "sproutingplant"

    print(f"\nFetching article: {slug} from {subdomain}.substack.com ...")
    article = fetch_article(subdomain, slug)
    print(f"Title: {article['title']}")

    print("\nGenerating slide scripts with GPT-4o ...")
    slides = generate_slide_scripts(client, article)
    print(f"Generated {len(slides)} slide scripts.")

    out_dir = Path("output") / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "slide_scripts.json").write_text(json.dumps(slides, indent=2))

    fonts = load_fonts()
    total = len(slides)

    print(f"\nGenerating {total} slides (background + text composite) ...")
    for slide in slides:
        n = slide["slide"]
        print(f"  Generating background for slide {n}/{total} ...")
        bg = generate_background(client, slide["visual_direction"])
        final = composite_text(bg, slide, fonts, n, total)
        img_path = out_dir / f"slide_{n:02d}.png"
        final.save(img_path, "PNG")
        print(f"  ✓ Slide {n} saved → {img_path.name}")

    print(f"\nDone! All slides in: {out_dir.resolve()}")
    print("\nSlide scripts:")
    for s in slides:
        print(f"  [{s['slide']}] {s['headline']} — {s['body'][:60]}...")


if __name__ == "__main__":
    main()

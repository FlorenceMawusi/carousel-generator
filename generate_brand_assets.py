#!/usr/bin/env python3
"""
Generate Facebook/Instagram profile picture + cover photo options
in the AI and Spirituality brand palette.
"""

import os
import base64
from pathlib import Path
from openai import OpenAI

PROFILE_PROMPTS = [
    "Minimalist logo icon, abstract spiral loop made of two interlocking arcs, "
    "one cream-white (#F5F0E8) one red-orange (#E8440A), on a deep dark brown-black "
    "background (#1A1008). Geometric, clean, modern spiritual/tech symbol. "
    "Square format, centered, works well small. No text.",

    "Minimalist logo icon, a single glowing geometric flower-of-life style mark "
    "in warm gold (#C8860A) and red-orange (#E8440A) line work, on deep dark brown-black "
    "background (#1A1008). Sacred geometry meets modern tech aesthetic. "
    "Square format, centered, works well small. No text.",

    "Minimalist logo icon, a circuit-board pattern merging into a lotus/flower shape, "
    "red-orange (#E8440A) and gold (#C8860A) lines on deep dark brown-black background "
    "(#1A1008). Represents AI meeting spirituality. Square format, centered, clean. No text.",
]

COVER_PROMPTS = [
    "Wide banner image, moody dark editorial photography style, deep brown-black background "
    "(#1A1008) with a subtle red-orange (#E8440A) glowing spiral or loop motif on one side, "
    "lots of negative space for text overlay, cinematic atmosphere, gold (#C8860A) light accents. "
    "No text, no people. Wide aspect ratio.",

    "Wide banner image, abstract cosmic/spiritual scene, dark background (#1A1008), "
    "subtle nebula or constellation texture rendered in warm red-orange (#E8440A) and gold "
    "(#C8860A) tones instead of blue/purple, minimal and moody. No text, no people. Wide aspect ratio.",
]


def generate_image(client: OpenAI, prompt: str, size: str, out_path: Path):
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality="medium",
        n=1,
    )
    img_data = base64.b64decode(response.data[0].b64_json)
    out_path.write_bytes(img_data)
    print(f"  ✓ Saved → {out_path}")


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        return
    client = OpenAI(api_key=api_key)

    out_dir = Path("brand-assets")
    out_dir.mkdir(exist_ok=True)

    print("Generating profile picture options (1024x1024) ...")
    for i, prompt in enumerate(PROFILE_PROMPTS, 1):
        generate_image(client, prompt, "1024x1024", out_dir / f"profile_option_{i}.png")

    print("\nGenerating cover photo options (1536x1024, will need cropping to FB cover ratio) ...")
    for i, prompt in enumerate(COVER_PROMPTS, 1):
        generate_image(client, prompt, "1536x1024", out_dir / f"cover_option_{i}.png")

    print(f"\nDone! Check {out_dir.resolve()}")


if __name__ == "__main__":
    main()

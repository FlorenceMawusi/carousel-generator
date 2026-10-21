#!/usr/bin/env python3
"""Retry profile option 3 with explicit dark fill background."""

import os
import base64
from pathlib import Path
from openai import OpenAI

PROMPT = (
    "Minimalist logo icon, a circuit-board pattern merging into a lotus/flower shape, "
    "red-orange (#E8440A) and gold (#C8860A) lines, filled solid deep dark brown-black "
    "background (#1A1008) covering the entire square canvas edge to edge — NOT white, "
    "NOT transparent, NOT light colored. The background must be dark everywhere. "
    "Represents AI meeting spirituality. Square format, centered, clean. No text."
)


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        return
    client = OpenAI(api_key=api_key)

    out_dir = Path("brand-assets")
    out_dir.mkdir(exist_ok=True)

    print("Generating profile option 3 (dark fill retry) ...")
    response = client.images.generate(
        model="gpt-image-1",
        prompt=PROMPT,
        size="1024x1024",
        quality="medium",
        n=1,
    )
    img_data = base64.b64decode(response.data[0].b64_json)
    out_path = out_dir / "profile_option_3_dark.png"
    out_path.write_bytes(img_data)
    print(f"  ✓ Saved → {out_path}")


if __name__ == "__main__":
    main()

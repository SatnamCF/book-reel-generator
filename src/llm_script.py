"""Generate slide content for a book reel using Claude.

Output schema (per slide):
    type:          "hook" | "summary" | "cta"
    headline:      bold white text shown overlaid on the photo (5-10 words)
    image_prompt:  detailed prompt for Gemini Imagen (cinematic, photorealistic, 9:16)
    voiceover:     conversational narrator line (8-12 words)
"""
from __future__ import annotations

import json
import math
import os
import re

import anthropic

MODEL = "claude-sonnet-4-5"
WORDS_PER_SECOND = 2.3


SYSTEM_PROMPT = """You write punchy Instagram Reel scripts that summarize non-fiction books.

You return THREE things per slide:
1. A short on-screen headline (5-10 words, bold and quotable).
2. A detailed photorealistic image prompt for an AI image generator. The image MUST literally depict the metaphor or scene of the headline — when a viewer looks at the photo and reads the headline, they should immediately feel the connection.
3. A spoken voiceover line (8-12 words, conversational).

CRITICAL: HOOK SLIDE (slide 1) must STOP THE SCROLL in the first second.
The hook headline AND voiceover must be one of these patterns:
- A controversial / counterintuitive claim ("Money won't make you happy. Buying back your time will.")
- A pointed question that creates a curiosity gap ("Why do 92% of people quit before they win?")
- A pattern interrupt that names what the viewer is doing ("Stop scrolling. This will change your year.")
- A specific shocking stat ("99% of millionaires didn't inherit a cent.")
- A direct callout ("Still trading time for money? Read this.")
Avoid generic opener words like "Here's", "Today", "In this video". Open mid-thought, with attitude.

CRITICAL: image_prompt must visually match the headline.
- Headline "Two dads. Two money mindsets." → image_prompt: "Split-screen cinematic photo of two middle-aged men: LEFT is exhausted in a fluorescent-lit beige cubicle drowning in paperwork; RIGHT is relaxed on a sunny patio with a tablet showing investment charts. Vertical 9:16, photorealistic."
- Headline "Stop trading time for money." → image_prompt: "Cinematic photo of a young man head-in-hands hunched over a laptop late at night, harsh blue screen glow on his tired face, crumpled receipts and a calculator scattered on a dark desk. Vertical 9:16, photorealistic."
- Headline "Build assets that pay you while you sleep." → image_prompt: "Cinematic photo of a relaxed man in linen on a luxury rooftop terrace at sunset, holding a tablet, golden-hour city skyline behind him with subtle floating dollar bills and a green upward trending arrow graphic. Vertical 9:16, photorealistic."

Image prompt requirements:
- Always cinematic, photorealistic, hyperreal, professional photography.
- ONE specific scene with a clear human subject when relevant.
- Specify lighting, mood, time of day, location.
- Vertical 9:16 framing.
- NO text in the image (text is overlaid in post — explicitly say "no text, no captions, no signage").
- Vary scenes across slides — never repeat a setting.

Output ONLY valid JSON. No prose, no markdown fences."""


def _user_prompt(book: str, duration: int, n_slides: int, total_words: int) -> str:
    return f"""Book: "{book}"
Target video duration: {duration} seconds.
Number of slides: exactly {n_slides}.
Total voiceover words across all slides: ~{total_words} (split roughly evenly).

Return JSON:

{{
  "book": "<full title>",
  "author": "<author name>",
  "slides": [
    {{
      "type": "hook" | "summary" | "cta",
      "headline": "<5-10 words, bold quotable text shown on the slide>",
      "image_prompt": "<detailed cinematic photorealistic image description>",
      "voiceover": "<8-12 words, conversational narration>"
    }}
  ]
}}

Rules:
- Slide 1 is "hook" — controversial/intriguing claim.
- Last slide is "cta" — push to read the book; image_prompt should show the physical book on a desk/shelf with warm lighting.
- Middle slides are "summary" — one big idea each, contrasting visual.
- Headline is what's overlaid on the photo (not the same text as voiceover).
- Image prompts should vary scene/setting across slides — don't repeat the same location.
- All image prompts must include "vertical 9:16, photorealistic"."""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def generate(book: str, duration_seconds: int) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    n_slides = max(4, math.ceil(duration_seconds / 4.5))
    total_words = int(duration_seconds * WORDS_PER_SECOND)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=os.environ.get("REEL_MODEL", MODEL),
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_prompt(book, duration_seconds, n_slides, total_words)}],
    )
    raw = message.content[0].text
    parsed = json.loads(_strip_code_fences(raw))

    if "slides" not in parsed or not isinstance(parsed["slides"], list):
        raise ValueError(f"Claude returned malformed JSON (no slides): {raw[:300]}")
    if len(parsed["slides"]) != n_slides:
        parsed["slides"] = parsed["slides"][:n_slides]

    return parsed

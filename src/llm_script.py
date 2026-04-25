"""Generate slide content for a book reel using Claude.

Returns a strict JSON structure that downstream renderers consume.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass

import anthropic

MODEL = "claude-sonnet-4-5"  # cheap + capable; override via env if you want Opus
WORDS_PER_SECOND = 2.3  # ~140 wpm — engaging-reel pace


@dataclass
class SlideJob:
    book: str
    duration_seconds: int


SYSTEM_PROMPT = """You write punchy, viral-style Instagram Reel scripts that summarize non-fiction books.

Style:
- Short, bold, contrast-driven copy. Think Rich Dad Poor Dad style.
- Each slide has a strong takeaway, not a paragraph.
- Hook first, payoff middle, CTA last.
- Voiceover is conversational and ~8-12 words per slide.
- Body text on slide REINFORCES or CONTRASTS the voiceover — it does NOT repeat it.
- Use ALL-CAPS sparingly for the punch words.

Output ONLY valid JSON matching the requested schema. No prose, no markdown fences."""


def _user_prompt(book: str, duration: int, n_slides: int, total_words: int) -> str:
    return f"""Create an Instagram Reel script for the book: "{book}"

Target video duration: {duration} seconds.
Number of slides: exactly {n_slides}.
Total voiceover words across all slides: ~{total_words} (split roughly evenly).

Schema (return JSON, nothing else):

{{
  "book": "<full book title>",
  "author": "<author name>",
  "slides": [
    {{
      "type": "hook" | "summary" | "cta",
      "voiceover": "<8-12 words, conversational, what the narrator says>",
      "body_lines": [
        {{"text": "<short line>", "size": "small" | "medium" | "large" | "huge", "color": "white" | "muted" | "gold" | "red" | "green"}}
      ],
      "theme": "hero_word" | "split" | "rising" | "rays" | "rings" | "silhouette",
      "theme_word": "<single character/symbol/short word for hero_word theme; otherwise empty string>",
      "accent_color": "gold" | "red" | "green" | "blue" | "purple"
    }}
  ]
}}

Rules:
- Slide 1 is type "hook" — a controversial or counter-intuitive claim from the book.
- Last slide is type "cta" — push to read the book, ends with "LINK IN BIO" or similar.
- Middle slides are "summary" — one big idea each, with a contrast or punchline.
- 4-8 body_lines per slide. Use empty strings ({{"text": "", ...}}) sparingly for spacing.
- Pick "theme" based on slide content:
  - hero_word: when there's a single dominant symbol (money "$", brain, fire). Set theme_word.
  - split: when contrasting two ideas (rich vs poor, then vs now)
  - rising: growth, success, wealth, momentum
  - rays: revelation, insight, breakthrough, the "aha"
  - rings: cycles, loops, traps, repetition
  - silhouette: a single archetypal object/figure
- Vary themes across slides — don't repeat the same theme back-to-back.
- accent_color is the highlight color for the punch line on that slide."""


def _strip_code_fences(text: str) -> str:
    """Claude sometimes wraps JSON in ```json ... ``` even when told not to."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def generate(book: str, duration_seconds: int) -> dict:
    """Call Claude and return the parsed slide JSON."""
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
        # Trim or warn — trim is safer than failing on a 1-slide drift
        parsed["slides"] = parsed["slides"][:n_slides]

    return parsed

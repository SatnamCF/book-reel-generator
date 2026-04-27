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

CRITICAL: image_prompt must literally depict the headline.

Image-prompt construction recipe (use this every time):
1. Identify the LITERAL subject + emotion in the headline.
2. Build a single cinematic scene that someone glancing at the photo would
   immediately match to the headline — no abstract concepts, no random
   stock-photo vibes.
3. Specify: subject (who/what), action/pose, location, lighting, time of day,
   camera framing. Concrete > abstract every time.
4. End with: "Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text, no captions, no signage."

Examples (headline → image_prompt):
- "Two dads. Two money mindsets." → "Split-screen cinematic photo. LEFT: exhausted middle-aged man in a fluorescent-lit beige cubicle, head in hands, surrounded by stacked paperwork. RIGHT: same age man relaxed on a sunny patio, tablet showing rising investment charts, palm tree shadow. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."
- "Stop trading time for money." → "Cinematic photo of a young man head-in-hands hunched over a laptop at 2am, harsh blue screen glow on his tired face, crumpled receipts and an analog clock at 2:00 on a dark cluttered desk. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."
- "Build assets that pay you while you sleep." → "Cinematic photo of a relaxed man in linen sleeping on a hammock at golden hour, smartphone on his chest showing a green stock chart, lush tropical resort and ocean behind him. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."
- "You're not special. And that's liberating." → "Cinematic aerial photo of a single tiny human silhouette walking across an enormous empty white salt flat at sunrise, casting a long shadow, scale dwarfed by the vast emptiness. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."

Image prompt requirements (MANDATORY):
- LITERAL subject from the headline must appear in the photo.
- Always exactly ONE coherent single-frame scene. NEVER request: split-screen, side-by-side, diptych, two-panel, before/after, comparison, collage, mirrored composition. These force each half into a narrower-than-portrait area which makes Flux elongate the subjects vertically.
- Specify lighting, time of day, location, framing — and these must align with the book's visual_theme.
- Always end with this EXACT tail: "Vertical portrait 9:16, photorealistic, hyperreal, cinematic, anatomically correct natural human proportions, no distortion, no elongation, no stretched limbs or bodies, no tall thin figures, sharp focus, professional photography, no text, no captions, no signage."
- Vary the SCENE across slides (different locations/subjects), but keep the AESTHETIC consistent (same lighting palette, same photographic style, same mood from the visual_theme).

Handling CONTRAST headlines without split-screens:
- For "X vs Y" headlines (e.g., "Rich vs Poor mindset", "Fear vs Courage"), pick ONE side and depict it in a single full-frame scene. The headline + voiceover already carries the contrast — the photo only needs to embody ONE pole of it powerfully.
- Example: "Fear keeps you poor. Courage builds wealth." → "Cinematic photo of a confident businesswoman in her 40s standing at a sunlit corner office window, arms relaxed, calm decisive expression, Manhattan skyline in soft focus behind her, golden hour light. Medium shot from waist up." (Embodies courage; fear is implied by contrast.)

For human subjects, framing must be SAFE for AI image generation. Strict rules:
- ALWAYS use one of: "medium shot from waist up", "chest-up portrait", "head and shoulders", "seated at a desk", "leaning on a counter", "standing facing camera in natural pose".
- NEVER request these poses — they reliably trigger Flux/SDXL to elongate necks, limbs, or torsos:
  * "looking up at [sky/lights/ceiling]" (elongates neck)
  * "head tilted back" (elongates neck)
  * "reaching up" / "arms raised overhead" (elongates arms)
  * "standing on tiptoe" / "jumping" / "mid-air" (elongates legs)
  * "stretching" / "yoga pose" / "running" (any extended pose)
  * "full body shot" / "head-to-toe" of a standing person (always elongates)
  * "tall figure" / "towering" / "elongated shadow" (literally asks for stretch)
- If the headline calls for a dynamic feel, convey it via LIGHTING and EXPRESSION, not pose. E.g., "intense focused expression, sweat on brow, dramatic rim light" instead of "athlete jumping for the rim".
- Subjects should look NATURAL and STILL — like a portrait photographer's shot, not an action photographer's.

Output ONLY valid JSON. No prose, no markdown fences."""


def _user_prompt(book: str, duration: int, n_slides: int, total_words: int) -> str:
    return f"""Book: "{book}"
Target video duration: {duration} seconds.
Number of slides: exactly {n_slides}.
Total voiceover words across all slides: ~{total_words} (split roughly evenly).

STEP 1 (think before writing slides): decide the BOOK'S VISUAL THEME. This is
the cohesive aesthetic that all 7 photos in this reel must share. Think like
a creative director picking a mood board.

Examples of good visual_theme strings:
- Rich Dad Poor Dad → "Luxury vs hustle: golden-hour business photography. Marble lobbies, rooftop terraces, suits, sports cars contrasted with cluttered cubicles, late-night laptops, drained faces. Warm gold highlights, deep navy shadows."
- Atomic Habits → "Modern minimalist productivity. Soft natural daylight, scandinavian/japandi interiors, clean wooden desks, single subjects in calm focused moments. Muted earth tones, lots of negative space."
- The Subtle Art of Not Giving a F*ck → "Raw urban realism. Candid street photography, gritty city scenes, honest unstaged moments, neon-and-rain night vibes. Slightly desaturated, high contrast, photojournalism feel."
- Atomic Awakening / Power of Now → "Spiritual stillness. Misty mountain dawns, lone figures in vast landscapes, soft ethereal light, monk-like solitude. Muted blues and warm whites."
- Cant Hurt Me / Relentless → "Dark intensity. Athletes training in dim gyms, sweat, single dramatic spotlights, rain, predawn workouts, gritted teeth. Deep blacks, harsh rim lighting."

STEP 2: for every slide's image_prompt, weave in the visual_theme palette,
lighting, and aesthetic alongside the literal subject from the headline.

Return JSON:

{{
  "book": "<full title>",
  "author": "<author name>",
  "visual_theme": "<one-paragraph mood-board description that all photos share>",
  "slides": [
    {{
      "type": "hook" | "summary" | "cta",
      "headline": "<5-10 words, bold quotable text shown on the slide>",
      "image_prompt": "<scene literal to headline, styled per visual_theme>",
      "text_position": "top" | "center" | "bottom",
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
- All image prompts must include "vertical 9:16, photorealistic".

text_position rules — pick based on where the photo's MAIN SUBJECT sits:
- "top" — subject in the lower half of the frame (sky/ceiling above is empty). Text reads cleanly above the subject. Examples: a person sitting on a beach with sky above; a tiny figure in vast space; subject at frame's bottom edge.
- "bottom" — subject in the upper half of the frame (foreground/floor below is empty). Text drops in below the subject. Examples: bird's-eye shot of a desk with empty foreground; portrait with chest-up framing; mountain peak with empty lower foreground.
- "center" — subject fills the frame OR is centered AND the headline is short enough to land cleanly mid-image. Use sparingly — usually one of "top" or "bottom" wins.
- For the CTA slide, ALWAYS use "top" so the gold pill button doesn't collide with text."""


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

"""Generate slide content for a book reel using Claude.

Output schema (per slide):
    type:           "hook" | "summary" | "cta"
    headline:       bold white text shown overlaid on the photo (5-10 words)
    image_prompt:   detailed prompt for the image generator (cinematic, photorealistic, 9:16)
    text_position:  "top" | "center" | "bottom" — where headline sits on slide
    voiceover:      conversational narrator line (8-12 words)
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

ABSOLUTE RULE: NO HUMAN SUBJECTS in any image_prompt. The free AI image
model we use cannot render humans in 9:16 portrait without distorting
their proportions — they always get vertically stretched. Therefore:
every image must depict OBJECTS, SCENES, or ENVIRONMENTS — never a
person as the subject.

ALLOWED object/scene categories (use these creatively):
  * Items on a surface: books, cash, coins, watch, keys, wallet, phone, laptop, papers, pen, calculator, coffee cup
  * Architectural interiors: corner office, marble lobby, empty boardroom, hotel suite, library, art gallery
  * Architectural exteriors: city skyline, rooftop terrace, modern building facade, suburban house, neon-lit alley
  * Landscapes: mountain peak at dawn, vast desert, ocean horizon, misty forest, salt flats
  * Vehicles: vintage sports car, classic motorcycle, private jet, yacht
  * Close-ups of materials: marble, wood grain, leather, fabric, water surface
  * Hands-only compositions (no face/body): "hands typing on a laptop", "hands signing a document", "hands holding a stack of cash"
  * Abstract weather/time: golden hour light through windows, neon rain at night, predawn fog

NEVER write any of these in an image_prompt:
  * Person, man, woman, boy, girl, child, kid, individual, figure, silhouette of a person
  * Businessman, businesswoman, executive, employee, worker, professional, athlete, entrepreneur
  * Any descriptor like "young", "middle-aged", "elderly" attached to a subject
  * "Standing", "sitting", "walking", "running" (these all imply human posture)
  * Body parts beyond hands: face, head, eyes, neck, shoulders, torso, legs, feet
  * Crowds, audiences, groups of people

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

Examples (headline → image_prompt) — every example is OBJECT-FIRST or SCENE-FIRST. Zero humans:
- "Two dads. Two money mindsets." → "Cinematic wide shot of an empty corner office at golden hour, two leather chairs facing each other across a polished wooden desk, one chair has a pile of crumpled bills and a calculator, the other has an open laptop showing a rising stock chart and a fresh espresso. Manhattan skyline through floor-to-ceiling windows, warm sunlight streaming in, marble floor in foreground. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."
- "Stop trading time for money." → "Cinematic close-up of an analog wall clock reading 2:00 AM in a dimly lit home office, harsh blue laptop glow on a cluttered desk below, scattered receipts and a half-empty coffee cup, ceiling lamp casting a warm pool of light, deep shadows around the edges. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."
- "Build assets that pay you while you sleep." → "Cinematic wide shot of an empty hammock swaying between two palm trees on a private tropical beach at golden hour, smartphone resting on the hammock displaying a bright green stock chart, calm ocean horizon and pastel sunset sky behind, white sand in the foreground. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."
- "You're not special. And that's liberating." → "Cinematic wide aerial drone shot of an empty wooden bench at the edge of an enormous white salt flat at sunrise, immense empty pastel sky above, single long shadow stretching across the cracked white surface, vast emptiness extending to the horizon. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, no text."
- "Read the book that rewrote my money story." (CTA) → "Cinematic close-up of a hardcover book standing upright on a polished wooden desk under a warm vintage desk lamp, leather armchair and a dusk city skyline visible through a window in soft focus behind, golden ambient light. Vertical portrait 9:16, photorealistic, hyperreal, cinematic, sharp focus, no text."

Image prompt requirements (MANDATORY):
- LITERAL subject from the headline must appear in the photo.
- Always exactly ONE coherent single-frame scene. NEVER request: split-screen, side-by-side, diptych, two-panel, before/after, comparison, collage, mirrored composition. These force each half into a narrower-than-portrait area which makes Flux elongate the subjects vertically.
- Specify lighting, time of day, location, framing — and these must align with the book's visual_theme.
- Always end with this EXACT tail: "Vertical portrait 9:16, photorealistic, hyperreal, cinematic, anatomically correct natural human proportions, no distortion, no elongation, no stretched limbs or bodies, no tall thin figures, sharp focus, professional photography, no text, no captions, no signage."
- Vary the SCENE across slides (different locations/subjects), but keep the AESTHETIC consistent (same lighting palette, same photographic style, same mood from the visual_theme).

Handling CONTRAST headlines without split-screens:
- For "X vs Y" headlines (e.g., "Rich vs Poor mindset", "Fear vs Courage"), pick ONE side and depict it in a single full-frame scene. The headline + voiceover already carries the contrast — the photo only needs to embody ONE pole of it powerfully.
- Example: "Fear keeps you poor. Courage builds wealth." → "Cinematic photo of a confident businesswoman in her 40s standing at a sunlit corner office window, arms relaxed, calm decisive expression, Manhattan skyline in soft focus behind her, golden hour light. Medium shot from waist up." (Embodies courage; fear is implied by contrast.)

Composition rules (apply to all object/scene shots):
- Subject (the object or focal element) occupies the center 50-60% of the frame, never fills it edge-to-edge.
- Generous environmental context above and below the focal element.
- Wide environmental shot, never extreme close-up.
- Convey emotional weight via LIGHTING (warm/cool, harsh/soft, dawn/dusk/midnight) and SETTING (luxury office, gritty street, empty hammock), not via human expression.

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
      "hook_subline": "<HOOK SLIDE ONLY: 6-12 word teaser promising payoff, e.g. '3 ideas that will reset how you think →' or 'The answer will surprise you. Watch till the end.' Empty string for non-hook slides.>",
      "image_prompt": "<scene literal to headline, styled per visual_theme — used by AI image gen if enabled>",
      "image_search_query": "<2-5 keyword search query for Pexels stock photos, e.g. 'luxury rooftop sunset' or 'stressed laptop late night' or 'open book desk lamp'>",
      "text_position": "top" | "center" | "bottom",
      "voiceover": "<8-12 words, conversational narration>"
    }}
  ]
}}

CRITICAL — the hook_subline (slide 1 only):
A small text under the main hook headline that creates a CURIOSITY GAP and
PROMISES PAYOFF. Without it, people see the bold claim and scroll. With it,
they stay because they want the answer/list/insight.

Patterns that work:
- Numbered promise: "3 lessons that changed everything →"
- Tease the answer: "The fix is the opposite of what you'd think."
- Watch-till-end hook: "Slide 4 is the one that hit me hardest."
- Save-for-later trigger: "Save this. You'll come back to slide 5."
- Direct stakes: "Get this wrong and you stay broke."

Keep it 6-12 words. Lowercase or sentence-case (NOT all-caps — the chip and
headline above already do the shouting). Empty string ("") for slides 2+.

CRITICAL: image_search_query must be SHORT and CONCRETE — keywords a stock-photo site would index, not a sentence. Examples:
- Headline "Two dads. Two money mindsets." → "luxury office sunset" or "marble corner office"
- Headline "Stop trading time for money." → "tired laptop late night" or "midnight desk receipts"
- Headline "Build assets that pay you while you sleep." → "tropical hammock beach sunset" or "infinity pool overlooking ocean"
- Headline "You're not special." → "salt flat empty horizon" or "lone bench desert"
- Headline (CTA) "Read this book." → "open book wooden desk" or "leather chair library lamp"
Pick keywords that match the headline's emotional tone AND the book's visual_theme.

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

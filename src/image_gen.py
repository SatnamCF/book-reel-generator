"""Generate slide background images.

Default provider: **Pexels** — real photographs, no AI distortion.
Searched by per-slide keywords from the LLM. Free, requires PEXELS_API_KEY.

Free fallback: **Pollinations.ai** (Flux). Photorealistic AI images but they
visibly stretch in 9:16 portrait because Flux was trained primarily on square
ratios. Use only if you can't get a Pexels key.

Optional: **Google Gemini** (`gemini-2.5-flash-image`) — requires Google
billing enabled.

A slide's `image_url` (when present) always wins, used by test fixtures so the
renderer runs offline.
"""
from __future__ import annotations

import io
import json
import os
import urllib.parse
import urllib.request

from PIL import Image, ImageFilter

W, H = 1080, 1920


def _fit_cover(img: Image.Image, w: int = W, h: int = H) -> Image.Image:
    src_w, src_h = img.size
    if (src_w, src_h) == (w, h):
        return img
    src_ratio = src_w / src_h
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_h = h
        new_w = int(new_h * src_ratio)
    else:
        new_w = w
        new_h = int(new_w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def from_url(url: str, timeout: int = 60, headers: dict | None = None) -> Image.Image:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "book-reel-generator/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    raw = Image.open(io.BytesIO(data)).convert("RGB")
    print(f"    [image_gen] downloaded {raw.size} from {url[:80]}...")
    fitted = _fit_cover(raw)
    if raw.size != fitted.size and (raw.size[0] < W or raw.size[1] < H):
        # Recover sharpness only when we upscaled
        fitted = fitted.filter(ImageFilter.UnsharpMask(radius=2.0, percent=80, threshold=2))
    return fitted


# ----------------------------- Pexels (default) -----------------------------


def from_pexels(query: str, slide_index: int = 0) -> Image.Image:
    """Search Pexels for portrait photos and pick a good one."""
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PEXELS_API_KEY is not set. Get a free key at https://www.pexels.com/api/ "
            "(takes 30 seconds), then add it as a GitHub Secret."
        )
    encoded = urllib.parse.quote(query.strip())
    # per_page=15 → enough variety; orientation=portrait → 9:16-friendly
    api_url = (
        f"https://api.pexels.com/v1/search?query={encoded}"
        f"&orientation=portrait&size=large&per_page=15"
    )
    req = urllib.request.Request(api_url, headers={"Authorization": api_key})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())

    photos = data.get("photos") or []
    if not photos:
        # No results — fall back to a more generic query (first word)
        first_word = query.strip().split()[0] if query.strip() else "abstract"
        if first_word != query.strip():
            print(f"    [image_gen] Pexels found 0 for '{query}'; retrying with '{first_word}'")
            return from_pexels(first_word, slide_index)
        raise RuntimeError(f"Pexels returned no photos for query: {query}")

    # Vary photo per slide so similar queries don't collide
    photo = photos[slide_index % len(photos)]
    # Use the largest portrait variant available
    img_url = photo["src"].get("portrait") or photo["src"].get("large2x") or photo["src"]["large"]
    print(f"    [image_gen] Pexels query '{query}' -> photographer {photo.get('photographer', '?')}")
    return from_url(img_url, timeout=60)


# ----------------------------- Pollinations (fallback) -----------------------------


def from_pollinations(prompt: str, seed: int = 42) -> Image.Image:
    """Pollinations.ai Flux. Free, no key, but stretches in 9:16."""
    SRC_W, SRC_H = 576, 1024
    prompt = (
        f"{prompt.rstrip('. ')}. "
        "Subject occupies center 50-60% of frame with generous empty space "
        "above and below. Anatomically correct natural human proportions, "
        "no distortion, no elongation, no stretched limbs or bodies, no tall "
        "thin figures, no split screens, single coherent scene, sharp focus."
    )
    encoded = urllib.parse.quote(prompt[:1800], safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={SRC_W}&height={SRC_H}&nologo=true&nofeed=true&model=flux&seed={seed}"
    )
    return from_url(url, timeout=120)


# ----------------------------- Gemini (paid) -----------------------------


def from_gemini(prompt: str, model: str | None = None) -> Image.Image:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or GEMINI_API_KEY) is not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    framed = (
        f"{prompt}\n\nComposition: tall vertical portrait orientation, 9:16 aspect ratio. "
        "Frame the subject so important content sits in the central vertical band."
    )
    response = client.models.generate_content(
        model=model or os.environ.get("REEL_IMAGE_MODEL", "gemini-2.5-flash-image"),
        contents=framed,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for candidate in response.candidates or []:
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                return _fit_cover(Image.open(io.BytesIO(part.inline_data.data)).convert("RGB"))
    raise RuntimeError(f"Gemini returned no image for prompt: {prompt[:120]}")


# ----------------------------- dispatch -----------------------------


def generate_for_slide(slide: dict, slide_index: int = 0) -> Image.Image:
    if slide.get("image_url"):
        return from_url(slide["image_url"])

    provider = os.environ.get("IMAGE_PROVIDER", "pexels").lower()

    if provider == "pexels":
        query = slide.get("image_search_query") or slide.get("headline", "")
        if not query:
            raise ValueError(f"Slide is missing image_search_query: {slide}")
        return from_pexels(query, slide_index=slide_index)

    if provider == "pollinations":
        prompt = slide.get("image_prompt")
        if not prompt:
            raise ValueError(f"Slide is missing image_prompt for Pollinations: {slide}")
        return from_pollinations(prompt, seed=42 + slide_index * 17)

    if provider == "gemini":
        prompt = slide.get("image_prompt")
        if not prompt:
            raise ValueError(f"Slide is missing image_prompt for Gemini: {slide}")
        return from_gemini(prompt)

    raise ValueError(f"Unknown IMAGE_PROVIDER: {provider}")

"""Generate slide background images via Google Gemini.

Uses `gemini-2.5-flash-image` (Nano Banana) — Google's multimodal image-gen
model, available on the FREE tier. (Imagen models require billing.)

Returns a 1080x1920 PIL.Image. Falls back to a URL fetch when a slide carries
`image_url` (used by test fixtures so the renderer runs without an API key).
"""
from __future__ import annotations

import io
import os
import urllib.request

from PIL import Image

W, H = 1080, 1920

# Free-tier image model. Set REEL_IMAGE_MODEL to override.
DEFAULT_MODEL = "gemini-2.5-flash-image"


def _fit_cover(img: Image.Image, w: int = W, h: int = H) -> Image.Image:
    """Resize-and-crop to W x H (preserves aspect, fills canvas)."""
    src_w, src_h = img.size
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


def from_url(url: str) -> Image.Image:
    with urllib.request.urlopen(url, timeout=30) as r:
        data = r.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return _fit_cover(img)


def from_gemini(prompt: str, model: str | None = None) -> Image.Image:
    """Call Gemini multimodal image gen and return a 1080x1920 PIL.Image."""
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or GEMINI_API_KEY) is not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    # gemini-2.5-flash-image doesn't accept aspect_ratio param — bake the hint
    # into the prompt and crop afterward to enforce 9:16.
    framed = (
        f"{prompt}\n\n"
        "Composition: tall vertical portrait orientation, 9:16 aspect ratio. "
        "Frame the subject so the important content sits in the central vertical band."
    )
    response = client.models.generate_content(
        model=model or os.environ.get("REEL_IMAGE_MODEL", DEFAULT_MODEL),
        contents=framed,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    for candidate in response.candidates or []:
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.data:
                pil = Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                return _fit_cover(pil)
    raise RuntimeError(f"Gemini returned no image for prompt: {prompt[:120]}")


def generate_for_slide(slide: dict) -> Image.Image:
    """Pick the right source: URL if set (testing), otherwise Gemini."""
    if slide.get("image_url"):
        return from_url(slide["image_url"])
    prompt = slide.get("image_prompt")
    if not prompt:
        raise ValueError(f"Slide is missing both image_url and image_prompt: {slide}")
    return from_gemini(prompt)

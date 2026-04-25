"""Generate slide background images via Google Gemini Imagen.

Returns a 1080x1920 PIL.Image for each prompt. Falls back to a URL fetch when
a slide carries `image_url` (used by the test fixtures to avoid spending API
calls during local testing).
"""
from __future__ import annotations

import io
import os
import urllib.request

from PIL import Image

W, H = 1080, 1920

# Imagen 4 (fast variant — cheaper, ~3-5s per image, good quality at 9:16).
# Override via env if you want the higher-quality slower variant.
DEFAULT_MODEL = "imagen-4.0-fast-generate-001"


def _fit_cover(img: Image.Image, w: int = W, h: int = H) -> Image.Image:
    """Resize-and-crop to W x H (preserves aspect, fills canvas)."""
    src_w, src_h = img.size
    src_ratio = src_w / src_h
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        # source is wider — fit height, crop width
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
    """Call Gemini Imagen and return a 1080x1920 PIL.Image."""
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY (or GEMINI_API_KEY) is not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_images(
        model=model or os.environ.get("REEL_IMAGE_MODEL", DEFAULT_MODEL),
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="9:16",
            person_generation="allow_adult",
        ),
    )
    if not response.generated_images:
        raise RuntimeError(f"Imagen returned no images for prompt: {prompt[:120]}")

    pil = response.generated_images[0].image._pil_image  # google-genai exposes the PIL underneath
    if pil is None:
        # Fallback path — read bytes and decode
        img_bytes = response.generated_images[0].image.image_bytes
        pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return _fit_cover(pil.convert("RGB"))


def generate_for_slide(slide: dict) -> Image.Image:
    """Pick the right source: URL if set (testing), otherwise Gemini."""
    if slide.get("image_url"):
        return from_url(slide["image_url"])
    prompt = slide.get("image_prompt")
    if not prompt:
        raise ValueError(f"Slide is missing both image_url and image_prompt: {slide}")
    return from_gemini(prompt)

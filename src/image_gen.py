"""Generate slide background images.

Default provider: **Pollinations.ai** — completely free, no API key required,
backed by Flux-Schnell. Returns 1080x1920 directly via URL parameters.

Optional provider: **Google Gemini** (`gemini-2.5-flash-image`) — requires
Google billing enabled (free tier has zero quota for image gen). Toggle with
env IMAGE_PROVIDER=gemini.

A slide's `image_url` (when present) always wins, used by test fixtures so the
renderer runs offline.
"""
from __future__ import annotations

import io
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


def from_url(url: str, timeout: int = 60) -> Image.Image:
    req = urllib.request.Request(url, headers={"User-Agent": "book-reel-generator/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    raw = Image.open(io.BytesIO(data)).convert("RGB")
    # Surface the actual returned dimensions so CI logs reveal any provider
    # weirdness (vs. the WxH we requested).
    print(f"    [image_gen] downloaded {raw.size} from {url[:80]}...")
    fitted = _fit_cover(raw)
    # Recover sharpness lost in the upscale (576x1024 -> 1080x1920 is 1.875x)
    if raw.size != fitted.size:
        fitted = fitted.filter(ImageFilter.UnsharpMask(radius=2.0, percent=80, threshold=2))
    return fitted


def from_pollinations(prompt: str, seed: int = 42) -> Image.Image:
    """Pollinations.ai — free, no key. Flux model.

    Empirical: Pollinations CAPS image output around 1024px on the long edge
    regardless of requested width/height. Flux's native 9:16 portrait size
    IS 576x1024, so we request that exactly and Lanczos-upscale to 1080x1920
    in PIL — one clean upscale, no stretch.

    Append "natural proportions" guards to the prompt to fight Flux's
    tendency to elongate human figures.
    """
    SRC_W, SRC_H = 576, 1024  # exact 9:16, Flux native
    # Belt-and-suspenders: ALWAYS append anatomy guards. Flux respects
    # late-prompt tokens, so even if Claude already included them, the
    # repetition strengthens the signal.
    prompt = (
        f"{prompt.rstrip('. ')}. "
        "Anatomically correct natural human proportions, no distortion, no elongation, "
        "no stretched limbs or bodies, no tall thin figures, no split screens, "
        "single coherent scene, sharp focus."
    )
    encoded = urllib.parse.quote(prompt[:1800], safe="")
    # nofeed bypasses Pollinations' public feed (and seems to dodge stale cached
    # responses that sometimes return wrong sizes).
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={SRC_W}&height={SRC_H}&nologo=true&nofeed=true&model=flux&seed={seed}"
    )
    return from_url(url, timeout=120)


def from_gemini(prompt: str, model: str | None = None) -> Image.Image:
    """Google Gemini image generation. Requires billing on the API project."""
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


PROVIDERS = {
    "pollinations": from_pollinations,
    "gemini": from_gemini,
}


def generate_for_slide(slide: dict, slide_index: int = 0) -> Image.Image:
    if slide.get("image_url"):
        return from_url(slide["image_url"])
    prompt = slide.get("image_prompt")
    if not prompt:
        raise ValueError(f"Slide is missing both image_url and image_prompt: {slide}")
    provider = os.environ.get("IMAGE_PROVIDER", "pollinations").lower()
    fn = PROVIDERS.get(provider, from_pollinations)
    if fn is from_pollinations:
        # Vary seed per slide so visually similar prompts don't collide
        return from_pollinations(prompt, seed=42 + slide_index * 17)
    return fn(prompt)

"""Render slides + voiceover + final MP4 with cinematic polish.

Per-slide layout:
  - Photo background fills 1080x1920
  - Subtle warm color grade for cohesive feel across slides
  - Cinematic top-down dark gradient (dark at top → clear at midline)
  - Soft corner vignette
  - Bold white headline near the top (top-anchored, multi-shadow)
  - On CTA slides: gold button + label near bottom

Video assembly:
  - Slow Ken Burns zoom per slide (alternating in/out)
  - 0.4s crossfade between slides
"""
from __future__ import annotations

import asyncio
import math
import textwrap
from pathlib import Path

import edge_tts
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import image_gen

W, H = 1080, 1920
VOICE = "en-US-GuyNeural"
FPS = 30
HEAD_PAD = 0.05
TAIL_PAD = 0.10
ZOOM_RANGE = 0.05
CROSSFADE = 0.4


# ----------------------------- fonts -----------------------------


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "segoeuib.ttf"]
        if bold
        else ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ----------------------------- photo polish -----------------------------


def _color_grade(img: Image.Image) -> Image.Image:
    """Subtle warm-highlight + slight cool-shadow grade. Adds 'pro' feel."""
    # Slight saturation boost
    img = ImageEnhance.Color(img).enhance(1.08)
    # Slight contrast lift
    img = ImageEnhance.Contrast(img).enhance(1.06)
    # Warm cast on highlights via channel curves
    r, g, b = img.split()
    r = r.point(lambda v: min(255, int(v + 8 * (v / 255))))
    b = b.point(lambda v: max(0, int(v - 4 * (v / 255))))
    return Image.merge("RGB", (r, g, b))


def _add_cinematic_gradient(img: Image.Image) -> Image.Image:
    """Dark top → clear midline. Cinema title-card legibility."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    grad_h = int(H * 0.62)
    for y in range(grad_h):
        t = y / grad_h
        # Ease-out: most opacity in top third, fades smoothly
        alpha = int(210 * (1 - t) ** 1.7)
        od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _add_bottom_gradient(img: Image.Image, max_alpha: int = 130) -> Image.Image:
    """Subtle dark band at very bottom — used on CTA slide."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    grad_h = int(H * 0.32)
    for i in range(grad_h):
        y = H - 1 - i
        t = i / grad_h
        alpha = int(max_alpha * (1 - t) ** 1.5)
        od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _add_vignette(img: Image.Image, strength: int = 80) -> Image.Image:
    """Soft radial darkening of corners — frames the subject."""
    mask = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(mask)
    cx, cy = W // 2, H // 2
    max_r = math.hypot(cx, cy)
    for i in range(40):
        r = max_r * (1 - i / 40) * 0.95
        alpha = 255 - int((i / 40) * strength)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(80))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(img, dark, mask)


# ----------------------------- text overlay -----------------------------


def _wrap_to_fit(text: str, font_size: int, max_width: int) -> tuple[list[str], int]:
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    def _wraps(size: int) -> list[str] | None:
        f = _font(size, bold=True)
        for wrap_chars in (28, 24, 22, 20, 18, 16):
            lines = textwrap.wrap(text, width=wrap_chars) or [text]
            widest = max((d.textbbox((0, 0), ln, font=f)[2] for ln in lines), default=0)
            if widest <= max_width and len(lines) <= 4:
                return lines
        return None

    for size in (font_size, font_size - 8, font_size - 16, font_size - 24):
        lines = _wraps(size)
        if lines:
            return lines, size
    return textwrap.wrap(text, width=18) or [text], max(font_size - 24, 48)


def _draw_headline(img: Image.Image, text: str, top_y: int = 260, font_size: int = 100, max_width: int = 920) -> Image.Image:
    """Top-anchored bold white headline, multi-shadow for legibility."""
    if not text:
        return img
    lines, actual_size = _wrap_to_fit(text, font_size, max_width)
    fnt = _font(actual_size, bold=True)
    ascent, descent = fnt.getmetrics()
    line_h = ascent + descent + 8
    d = ImageDraw.Draw(img)
    y = top_y
    for line in lines:
        # Outline + drop shadow stack for cinematic punch
        for dx, dy in ((5, 5), (3, 3), (-2, -2), (2, -2), (-2, 2)):
            d.text((W // 2 + dx, y + dy), line, font=fnt, fill=(0, 0, 0), anchor="mt")
        d.text((W // 2, y), line, font=fnt, fill=(255, 255, 255), anchor="mt")
        y += line_h
    return img


def _draw_cta(img: Image.Image, headline: str = "") -> Image.Image:
    """Premium CTA: bigger button, label above, more contrast."""
    img = _add_bottom_gradient(img, max_alpha=180)
    d = ImageDraw.Draw(img)

    # Small label above button
    f_label = _font(40, bold=True)
    label = "AVAILABLE NOW"
    d.text((W // 2, H - 380), label, font=f_label, fill=(255, 255, 255), anchor="mt")

    # Gold pill button with shadow
    btn_top, btn_bot = H - 320, H - 220
    # Drop shadow
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([130, btn_top + 6, W - 130, btn_bot + 6], radius=50, fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    img = Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB")
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([130, btn_top, W - 130, btn_bot], radius=50, fill=(255, 215, 100))
    f_btn = _font(50, bold=True)
    d.text((W // 2, (btn_top + btn_bot) // 2), "GRAB YOUR COPY  →", font=f_btn, fill=(40, 25, 10), anchor="mm")

    # Tiny "link in bio" hint below
    f_tiny = _font(30, bold=True)
    d.text((W // 2, H - 170), "↑  LINK IN BIO  ↑", font=f_tiny, fill=(255, 215, 100), anchor="mt")
    return img


def render_slide(slide: dict, slide_index: int = 0) -> Image.Image:
    photo = image_gen.generate_for_slide(slide, slide_index=slide_index)
    img = _color_grade(photo)
    img = _add_vignette(img, strength=80)
    img = _add_cinematic_gradient(img)
    img = _draw_headline(img, slide.get("headline", ""))
    if slide.get("type") == "cta":
        img = _draw_cta(img, slide.get("headline", ""))
    return img


# ----------------------------- voiceover -----------------------------


async def _synth_one(text: str, out_path: Path, rate: str) -> None:
    communicate = edge_tts.Communicate(text, VOICE, rate=rate)
    await communicate.save(str(out_path))


async def _synth_all(slides: list[dict], voice_dir: Path, rate: str) -> list[Path]:
    paths = []
    for i, slide in enumerate(slides):
        out = voice_dir / f"{i + 1:02d}.mp3"
        await _synth_one(slide["voiceover"], out, rate)
        paths.append(out)
    return paths


def synth_voiceovers(slides: list[dict], voice_dir: Path, rate: str = "+10%") -> list[Path]:
    voice_dir.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_synth_all(slides, voice_dir, rate))


def _calc_rate(total_words: int, target_seconds: int) -> str:
    if total_words == 0:
        return "+0%"
    available = max(1.0, target_seconds * 0.95)
    target_wpm = (total_words / available) * 60
    baseline_wpm = 115.0
    pct = round((target_wpm / baseline_wpm - 1.0) * 100)
    pct = max(-15, min(60, pct))
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct}%"


# ----------------------------- video assembly -----------------------------


def _zoom_clip(image_path: Path, duration: float, zoom_in: bool) -> CompositeVideoClip:
    base = ImageClip(str(image_path)).with_duration(duration).with_fps(FPS)
    if zoom_in:
        scale_fn = lambda t: 1.0 + ZOOM_RANGE * (t / duration)
    else:
        scale_fn = lambda t: 1.0 + ZOOM_RANGE - ZOOM_RANGE * (t / duration)
    zoomed = base.resized(scale_fn).with_position(("center", "center"))
    return CompositeVideoClip([zoomed], size=(W, H)).with_duration(duration).with_fps(FPS)


def assemble_video(slide_paths: list[Path], voice_paths: list[Path], out_path: Path) -> float:
    """Stitch with crossfades between consecutive slides."""
    visual_clips = []
    audio_clips = []
    cursor = 0.0

    for i, (slide_path, voice_path) in enumerate(zip(slide_paths, voice_paths)):
        voice = AudioFileClip(str(voice_path))
        slide_dur = HEAD_PAD + voice.duration + TAIL_PAD + (CROSSFADE if i < len(slide_paths) - 1 else 0)

        clip = _zoom_clip(slide_path, slide_dur, zoom_in=(i % 2 == 0))
        if i > 0:
            clip = clip.with_effects([CrossFadeIn(CROSSFADE)])
        clip = clip.with_start(cursor)
        visual_clips.append(clip)

        # Voice line starts at cursor + HEAD_PAD (after the crossfade has begun)
        audio_clips.append(voice.with_start(cursor + HEAD_PAD + (CROSSFADE / 2 if i > 0 else 0)))

        # Advance cursor accounting for the overlap
        cursor += slide_dur - (CROSSFADE if i < len(slide_paths) - 1 else 0)

    total_duration = cursor
    final_video = CompositeVideoClip(visual_clips, size=(W, H)).with_duration(total_duration)
    final_audio = CompositeAudioClip(audio_clips)
    final_video = final_video.with_audio(final_audio)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    final_video.write_videofile(
        str(out_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
    return total_duration


# ----------------------------- top-level -----------------------------


def render_all(content: dict, target_duration: int, work_dir: Path, out_path: Path) -> dict:
    slides = content["slides"]
    total_words = sum(len(s["voiceover"].split()) for s in slides)
    rate = _calc_rate(total_words, target_duration)

    slides_dir = work_dir / "slides"
    voice_dir = work_dir / "voiceover"
    slides_dir.mkdir(parents=True, exist_ok=True)

    slide_paths = []
    for i, slide in enumerate(slides):
        path = slides_dir / f"{i + 1:02d}.png"
        print(f"  Rendering slide {i + 1}/{len(slides)}: {slide.get('headline', '')[:60]}")
        render_slide(slide, slide_index=i).save(path, "PNG", optimize=True)
        slide_paths.append(path)

    voice_paths = synth_voiceovers(slides, voice_dir, rate=rate)
    duration = assemble_video(slide_paths, voice_paths, out_path)

    return {
        "book": content.get("book"),
        "author": content.get("author"),
        "n_slides": len(slides),
        "tts_rate": rate,
        "target_duration": target_duration,
        "actual_duration": round(duration, 2),
        "output": str(out_path),
    }

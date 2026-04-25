"""Render slides + voiceover + final MP4.

Layout per slide (matches the reference example style):
  - Photo background fills the 1080x1920 canvas
  - Dark gradient at the top for text legibility
  - Bold white headline near the top, centered, wrapped
  - On CTA slides: a gold "GRAB YOUR COPY" pill near the bottom
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import image_gen

W, H = 1080, 1920
VOICE = "en-US-GuyNeural"
FPS = 30
HEAD_PAD = 0.05
TAIL_PAD = 0.10
ZOOM_RANGE = 0.06


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


# ----------------------------- text overlay -----------------------------


def _add_text_band(img: Image.Image, center_y: int, half_height: int, max_alpha: int = 180) -> Image.Image:
    """Soft dark band centered on the text area for legibility on any photo."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for dy in range(-half_height, half_height + 1):
        # Cosine-falloff: full opacity at center, fades to 0 at edges
        falloff = 0.5 + 0.5 * math.cos((dy / half_height) * math.pi)
        alpha = int(max_alpha * falloff)
        y = center_y + dy
        if 0 <= y < H:
            od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(20))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _wrap_to_fit(text: str, font_size: int, max_width: int) -> tuple[list[str], int]:
    """Wrap text to fit max_width pixels at font_size. If still too wide, shrink size."""
    fnt = _font(font_size, bold=True)
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    def _wraps(size: int) -> list[str] | None:
        f = _font(size, bold=True)
        # Try wrap widths from generous to tight
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
    # Last resort
    return textwrap.wrap(text, width=18) or [text], max(font_size - 24, 48)


def _draw_headline(img: Image.Image, text: str, center_y: int = H // 2, font_size: int = 88, max_width: int = 940) -> Image.Image:
    """Draw headline centered both horizontally AND vertically on `center_y`.

    Uses anchor='mm' so each line is anchored at its visual middle, eliminating
    drift from font side-bearings. Adds a soft dark band behind the text for
    legibility regardless of underlying photo.
    """
    if not text:
        return img
    lines, actual_size = _wrap_to_fit(text, font_size, max_width)
    fnt = _font(actual_size, bold=True)

    # Compute total block height from line ascent/descent so vertical centering is exact
    ascent, descent = fnt.getmetrics()
    line_h = ascent + descent + 16  # 16px line spacing
    block_h = line_h * len(lines)

    # Add a band slightly larger than the text block
    img = _add_text_band(img, center_y=center_y, half_height=block_h // 2 + 60, max_alpha=180)

    d = ImageDraw.Draw(img)
    # Top of first line's middle anchor
    first_mid_y = center_y - block_h // 2 + line_h // 2
    for i, line in enumerate(lines):
        y = first_mid_y + i * line_h
        # Multi-direction shadow for extra legibility
        for dx, dy in ((4, 4), (-2, 2), (2, -2), (-2, -2)):
            d.text((W // 2 + dx, y + dy), line, font=fnt, fill=(0, 0, 0), anchor="mm")
        d.text((W // 2, y), line, font=fnt, fill=(255, 255, 255), anchor="mm")
    return img


def _draw_cta_button(img: Image.Image) -> Image.Image:
    d = ImageDraw.Draw(img)
    # Subtle dark scrim behind the button
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([60, H - 380, W - 60, H - 180], radius=50, fill=(0, 0, 0, 140))
    overlay = overlay.filter(ImageFilter.GaussianBlur(8))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    f_label = _font(44, bold=True)
    label = "LINK IN BIO"
    bbox = d.textbbox((0, 0), label, font=f_label)
    lw = bbox[2] - bbox[0]
    d.text(((W - lw) // 2, H - 350), label, font=f_label, fill=(255, 255, 255))

    # Gold pill button
    d.rounded_rectangle([140, H - 290, W - 140, H - 200], radius=45, fill=(255, 215, 100))
    f_btn = _font(46, bold=True)
    text = "GRAB YOUR COPY →"
    bbox = d.textbbox((0, 0), text, font=f_btn)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) // 2, H - 275), text, font=f_btn, fill=(40, 25, 10))
    return img


def render_slide(slide: dict, slide_index: int = 0) -> Image.Image:
    photo = image_gen.generate_for_slide(slide, slide_index=slide_index)
    # Text band is drawn inside _draw_headline (sized to the wrapped text).
    img = _draw_headline(photo, slide.get("headline", ""))
    if slide.get("type") == "cta":
        img = _draw_cta_button(img)
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
    video_clips = []
    audio_clips = []
    cursor = 0.0

    for i, (slide_path, voice_path) in enumerate(zip(slide_paths, voice_paths)):
        voice = AudioFileClip(str(voice_path))
        slide_dur = HEAD_PAD + voice.duration + TAIL_PAD
        clip = _zoom_clip(slide_path, slide_dur, zoom_in=(i % 2 == 0))
        video_clips.append(clip)
        audio_clips.append(voice.with_start(cursor + HEAD_PAD))
        cursor += slide_dur

    final_video = concatenate_videoclips(video_clips, method="compose")
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
    return cursor


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

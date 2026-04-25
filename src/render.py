"""Render slides + voiceover + final MP4 from the LLM JSON."""
from __future__ import annotations

import asyncio
import math
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

from .themes import W, H, render_background, _font

VOICE = "en-US-GuyNeural"
FPS = 30
HEAD_PAD = 0.05
TAIL_PAD = 0.10
ZOOM_RANGE = 0.06

SIZE_TO_PX = {"small": 44, "medium": 60, "large": 80, "huge": 108}
COLOR_MAP = {
    "white":  (252, 252, 252),
    "muted":  (215, 220, 230),
    "gold":   (255, 215, 100),
    "red":    (240, 95, 95),
    "green":  (110, 230, 155),
}


# ----------------------------- text rendering -----------------------------


def _draw_shadow(d: ImageDraw.ImageDraw, xy, text, fnt, fill, offset=5) -> None:
    x, y = xy
    for dx, dy in ((offset, offset), (-1, 1), (1, -1)):
        d.text((x + dx, y + dy), text, font=fnt, fill=(0, 0, 0))
    d.text((x, y), text, font=fnt, fill=fill)


def _measure_block(d, lines, spacing):
    total = 0
    for text, f, _ in lines:
        bbox = d.textbbox((0, 0), text or "X", font=f)
        total += (bbox[3] - bbox[1]) + spacing
    return total - spacing


def _add_text_scrim(img: Image.Image, top: int, bottom: int, opacity: int = 140) -> Image.Image:
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([60, top, W - 60, bottom], radius=40, fill=(0, 0, 0, opacity))
    overlay = overlay.filter(ImageFilter.GaussianBlur(8))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _draw_centered_block(img, body_lines, accent_for_largest):
    """Place body lines centered vertically with shadowed text and a dark scrim."""
    d = ImageDraw.Draw(img)
    rendered = []
    for line in body_lines:
        text = line.get("text", "")
        size_key = line.get("size", "medium")
        color_key = line.get("color", "white")
        size_px = SIZE_TO_PX.get(size_key, 60)
        color = COLOR_MAP.get(color_key, COLOR_MAP["white"])
        fnt = _font(size_px, bold=True)
        rendered.append((text, fnt, color))

    spacing = 20
    block_h = _measure_block(d, rendered, spacing)
    # Dark scrim sized to text block + padding
    pad = 80
    scrim_top = max(60, H // 2 - block_h // 2 - pad)
    scrim_bot = min(H - 60, H // 2 + block_h // 2 + pad)
    img = _add_text_scrim(img, scrim_top, scrim_bot, opacity=140)
    d = ImageDraw.Draw(img)

    y = H // 2 - block_h // 2
    for text, fnt, color in rendered:
        bbox = d.textbbox((0, 0), text or "X", font=fnt)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if text:
            _draw_shadow(d, ((W - tw) // 2, y), text, fnt, color)
        y += th + spacing
    return img


def _draw_cta_button(img: Image.Image) -> Image.Image:
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([140, H - 320, W - 140, H - 230], radius=45, fill=(255, 215, 100))
    f_btn = _font(44, bold=True)
    text = "GRAB YOUR COPY →"
    bbox = d.textbbox((0, 0), text, font=f_btn)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) // 2, H - 305), text, font=f_btn, fill=(40, 25, 10))
    return img


def render_slide(slide: dict) -> Image.Image:
    """Background + body text. CTA slides get the gold button."""
    bg = render_background(
        theme=slide.get("theme", "rays"),
        accent_color=slide.get("accent_color", "gold"),
        theme_word=slide.get("theme_word", ""),
    )
    img = _draw_centered_block(bg, slide.get("body_lines", []), slide.get("accent_color", "gold"))
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
    """Pick a TTS rate so the spoken audio fits the target duration.

    Empirically en-US-GuyNeural at +0% delivers ~115 wpm including its natural
    sentence-boundary pauses. We solve for the rate that hits target wpm,
    leaving a small pad for the slide head/tail.
    """
    if total_words == 0:
        return "+0%"
    # Reserve ~5% of duration for inter-slide pads
    available = max(1.0, target_seconds * 0.95)
    target_wpm = (total_words / available) * 60
    baseline_wpm = 115.0
    pct = round((target_wpm / baseline_wpm - 1.0) * 100)
    pct = max(-15, min(60, pct))  # edge-tts handles up to +100%; cap at +60% for legibility
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
    """Stitch slides + voiceovers into one MP4. Returns total duration."""
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


# ----------------------------- top-level orchestration -----------------------------


def render_all(content: dict, target_duration: int, work_dir: Path, out_path: Path) -> dict:
    """Run the full pipeline. Returns metadata about the output."""
    slides = content["slides"]
    total_words = sum(len(s["voiceover"].split()) for s in slides)
    rate = _calc_rate(total_words, target_duration)

    slides_dir = work_dir / "slides"
    voice_dir = work_dir / "voiceover"
    slides_dir.mkdir(parents=True, exist_ok=True)

    slide_paths = []
    for i, slide in enumerate(slides):
        path = slides_dir / f"{i + 1:02d}.png"
        render_slide(slide).save(path, "PNG", optimize=True)
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

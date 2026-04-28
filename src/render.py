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

# Instagram Reels safe areas — UI overlays cover these regions:
#   Top: back arrow + "Reels" label   → ~280px reserved
#   Bottom: profile pic + username + caption + audio → ~400px reserved
#   Right: like/comment/share/save column → ~140px reserved
# All text is positioned to stay clear of these regions.
SAFE_TOP = 280
SAFE_BOTTOM = 400
SAFE_RIGHT = 140
TEXT_MAX_WIDTH = W - 2 * SAFE_RIGHT  # 800px wide centered band


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


def _draw_headline(
    img: Image.Image,
    text: str,
    position: str = "top",
    font_size: int = 100,
    max_width: int = TEXT_MAX_WIDTH,
) -> Image.Image:
    """Bold white headline placed at top, center, or bottom of the slide.

    All positions respect Instagram Reels safe areas (SAFE_TOP, SAFE_BOTTOM,
    SAFE_RIGHT) so text never sits under the back-arrow, "Reels" label,
    profile pic / username, or right-side action icons.

    `position`:
        "top"    — top-anchored just below the SAFE_TOP region
        "center" — vertically centered around H/2 (within safe band)
        "bottom" — bottom-anchored just above the SAFE_BOTTOM region
    """
    if not text:
        return img
    lines, actual_size = _wrap_to_fit(text, font_size, max_width)
    fnt = _font(actual_size, bold=True)
    ascent, descent = fnt.getmetrics()
    line_h = ascent + descent + 8
    block_h = line_h * len(lines)

    if position == "center":
        first_y = H // 2 - block_h // 2 + line_h // 2
        anchor = "mm"
    elif position == "bottom":
        # Block ends just above the SAFE_BOTTOM region (with a small margin)
        last_y = H - SAFE_BOTTOM - 40
        first_y = last_y - block_h + line_h
        anchor = "mm"
    else:  # top
        first_y = SAFE_TOP + 40  # 40px breathing room below the back-arrow row
        anchor = "mt"

    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        if anchor == "mm":
            y = first_y + i * line_h
        else:
            y = first_y + i * line_h
        for dx, dy in ((5, 5), (3, 3), (-2, -2), (2, -2), (-2, 2)):
            d.text((W // 2 + dx, y + dy), line, font=fnt, fill=(0, 0, 0), anchor=anchor)
        d.text((W // 2, y), line, font=fnt, fill=(255, 255, 255), anchor=anchor)
    return img


def _draw_hook_headline(img: Image.Image, text: str, subline: str = "") -> Image.Image:
    """Slide 1 hook: gold chip + big white headline + optional curiosity-gap subline.

    All three elements sit below SAFE_TOP so they don't collide with
    Instagram's back-arrow + "Reels" header.
    """
    if not text:
        return img
    d = ImageDraw.Draw(img)

    # Gold "STOP SCROLLING" chip
    chip_text = "STOP SCROLLING"
    f_chip = _font(38, bold=True)
    chip_bbox = d.textbbox((0, 0), chip_text, font=f_chip)
    chip_w = chip_bbox[2] - chip_bbox[0]
    chip_h = chip_bbox[3] - chip_bbox[1]
    chip_pad_x, chip_pad_y = 28, 10
    chip_y = SAFE_TOP + 20
    d.rounded_rectangle(
        [
            W // 2 - chip_w // 2 - chip_pad_x,
            chip_y - chip_pad_y,
            W // 2 + chip_w // 2 + chip_pad_x,
            chip_y + chip_h + chip_pad_y,
        ],
        radius=30,
        fill=(255, 215, 100),
    )
    d.text((W // 2, chip_y + chip_h // 2), chip_text, font=f_chip, fill=(35, 25, 10), anchor="mm")

    # Big white headline below the chip
    lines, actual_size = _wrap_to_fit(text, 120, TEXT_MAX_WIDTH)
    fnt = _font(actual_size, bold=True)
    ascent, descent = fnt.getmetrics()
    line_h = ascent + descent + 8
    y = chip_y + chip_h + chip_pad_y + 60
    d = ImageDraw.Draw(img)
    for line in lines:
        for dx, dy in ((5, 5), (3, 3), (-2, -2), (2, -2), (-2, 2)):
            d.text((W // 2 + dx, y + dy), line, font=fnt, fill=(0, 0, 0), anchor="mt")
        d.text((W // 2, y), line, font=fnt, fill=(255, 255, 255), anchor="mt")
        y += line_h

    # Optional subline (curiosity-gap teaser) under the headline
    if subline:
        sub_y = y + 20  # 20px gap below the last headline line
        sub_lines, sub_size = _wrap_to_fit(subline, 50, TEXT_MAX_WIDTH)
        f_sub = _font(sub_size, bold=True)
        sub_ascent, sub_descent = f_sub.getmetrics()
        sub_line_h = sub_ascent + sub_descent + 4
        for sline in sub_lines:
            for dx, dy in ((3, 3), (-1, 1), (1, -1)):
                d.text((W // 2 + dx, sub_y + dy), sline, font=f_sub, fill=(0, 0, 0), anchor="mt")
            # Slightly warm/gold tint to differentiate from the main headline
            d.text((W // 2, sub_y), sline, font=f_sub, fill=(255, 230, 170), anchor="mt")
            sub_y += sub_line_h
    return img


def _draw_cta(img: Image.Image, book: str = "", author: str = "") -> Image.Image:
    """Premium CTA: book title + author + gold button + link-in-bio hint.

    All elements sit ABOVE the SAFE_BOTTOM region so Instagram's username,
    caption, and audio overlay don't cover them.

    Layout from top-of-CTA-block to bottom:
      [BOOK TITLE]   (large gold)
      by Author       (smaller white)
      [GRAB YOUR COPY →]   (gold pill)
      ↑ LINK IN BIO ↑      (gold tiny)
    """
    img = _add_bottom_gradient(img, max_alpha=200)
    d = ImageDraw.Draw(img)

    # Anchor the WHOLE CTA block above the bottom safe area.
    # Layout is built bottom-up:
    #   bottom edge of "LINK IN BIO" = H - SAFE_BOTTOM - 20
    link_bottom_y = H - SAFE_BOTTOM - 20
    f_tiny = _font(30, bold=True)
    link_text = "↑  LINK IN BIO  ↑"

    # button sits 30px above link
    btn_bot = link_bottom_y - 30 - 30  # link_text height ~30
    btn_top = btn_bot - 100
    # author 30px above button
    author_y_baseline = btn_top - 30
    # title above author
    title_baseline = author_y_baseline - 50

    # Book title — large, gold, wrapped to fit width
    title_block_h = 0
    if book:
        title_lines, title_size = _wrap_to_fit(book.upper(), 64, TEXT_MAX_WIDTH)
        f_title = _font(title_size, bold=True)
        ascent, descent = f_title.getmetrics()
        line_h = ascent + descent + 4
        title_block_h = line_h * len(title_lines)
        title_y = title_baseline - title_block_h
        for i, line in enumerate(title_lines):
            y = title_y + i * line_h
            for dx, dy in ((4, 4), (-2, 2), (2, -2)):
                d.text((W // 2 + dx, y + dy), line, font=f_title, fill=(0, 0, 0), anchor="mt")
            d.text((W // 2, y), line, font=f_title, fill=(255, 215, 100), anchor="mt")
    if author:
        f_author = _font(34, bold=False)
        for dx, dy in ((3, 3), (-1, 1)):
            d.text((W // 2 + dx, author_y_baseline + dy), f"by {author}", font=f_author, fill=(0, 0, 0), anchor="mt")
        d.text((W // 2, author_y_baseline), f"by {author}", font=f_author, fill=(245, 245, 245), anchor="mt")

    # Gold pill button with drop shadow — narrower so it clears right-side icons
    btn_left, btn_right = SAFE_RIGHT, W - SAFE_RIGHT
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([btn_left, btn_top + 6, btn_right, btn_bot + 6], radius=50, fill=(0, 0, 0, 140))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    img = Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB")
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([btn_left, btn_top, btn_right, btn_bot], radius=50, fill=(255, 215, 100))
    f_btn = _font(50, bold=True)
    d.text((W // 2, (btn_top + btn_bot) // 2), "GRAB YOUR COPY  →", font=f_btn, fill=(40, 25, 10), anchor="mm")

    # Link-in-bio hint
    d.text((W // 2, link_bottom_y - 30), link_text, font=f_tiny, fill=(255, 215, 100), anchor="mt")
    return img


def render_slide(slide: dict, slide_index: int = 0) -> Image.Image:
    photo = image_gen.generate_for_slide(slide, slide_index=slide_index)
    img = _color_grade(photo)
    img = _add_vignette(img, strength=80)
    img = _add_cinematic_gradient(img)
    if slide.get("type") == "hook":
        img = _draw_hook_headline(img, slide.get("headline", ""), slide.get("hook_subline", ""))
    else:
        # CTA always top so the gold pill at bottom doesn't collide
        position = "top" if slide.get("type") == "cta" else slide.get("text_position", "top")
        img = _draw_headline(img, slide.get("headline", ""), position=position)
    if slide.get("type") == "cta":
        img = _draw_cta(img, book=slide.get("_book", ""), author=slide.get("_author", ""))
    return img


# ----------------------------- voiceover -----------------------------


async def _synth_one(text: str, out_path: Path, rate: str) -> None:
    communicate = edge_tts.Communicate(text, VOICE, rate=rate)
    await communicate.save(str(out_path))


def _bump_rate(rate: str, extra_pct: int) -> str:
    """Add `extra_pct` to a rate like '+10%' → '+18%'. Caps at +100%."""
    sign = 1 if rate.startswith("+") else (-1 if rate.startswith("-") else 1)
    n = int(rate.strip("+-%"))
    new = sign * n + extra_pct
    new = max(-15, min(100, new))
    s = "+" if new >= 0 else ""
    return f"{s}{new}%"


async def _synth_all(slides: list[dict], voice_dir: Path, rate: str) -> list[Path]:
    """Same TTS rate for every slide. The hook punch comes from the visual
    treatment + the words themselves, not from speeding up speech (which
    sounds rushed on top of an already-tight base rate).
    """
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

    Capped at +20% to keep speech natural — better to overshoot the
    target by a few seconds than to speak in a rushed monotone.
    """
    if total_words == 0:
        return "+0%"
    available = max(1.0, target_seconds * 0.95)
    target_wpm = (total_words / available) * 60
    baseline_wpm = 115.0
    pct = round((target_wpm / baseline_wpm - 1.0) * 100)
    # Hard cap at +20% — anything faster sounds rushed
    pct = max(-15, min(20, pct))
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


def _hook_punch_clip(image_path: Path, duration: float) -> CompositeVideoClip:
    """Cinematic punch-in for the first slide.

    Starts at 1.10x and snaps to 1.0x in the first 0.3s with cubic ease-out
    (gives that 'thumb-stopping' impact landing), then drifts to 1.06x over
    the remainder for a continuous Ken Burns feel.
    """
    base = ImageClip(str(image_path)).with_duration(duration).with_fps(FPS)
    PUNCH_DUR = 0.3
    PUNCH_FROM = 1.10
    DRIFT_TO = 1.06

    def scale_fn(t):
        if t < PUNCH_DUR:
            progress = t / PUNCH_DUR
            ease = 1 - (1 - progress) ** 3
            return PUNCH_FROM - (PUNCH_FROM - 1.0) * ease
        post_t = (t - PUNCH_DUR) / max(0.001, duration - PUNCH_DUR)
        return 1.0 + (DRIFT_TO - 1.0) * post_t

    zoomed = base.resized(scale_fn).with_position(("center", "center"))
    return CompositeVideoClip([zoomed], size=(W, H)).with_duration(duration).with_fps(FPS)


def assemble_video(slide_paths: list[Path], voice_paths: list[Path], out_path: Path) -> float:
    """Stitch with crossfades between consecutive slides.

    Slide 1 gets special treatment: zero head-pad (voice starts immediately)
    and a punch-in zoom for thumb-stopping impact in the first 3 seconds.
    """
    visual_clips = []
    audio_clips = []
    cursor = 0.0

    for i, (slide_path, voice_path) in enumerate(zip(slide_paths, voice_paths)):
        voice = AudioFileClip(str(voice_path))
        is_hook = (i == 0)
        head = 0.0 if is_hook else HEAD_PAD
        slide_dur = head + voice.duration + TAIL_PAD + (CROSSFADE if i < len(slide_paths) - 1 else 0)

        if is_hook:
            clip = _hook_punch_clip(slide_path, slide_dur)
        else:
            clip = _zoom_clip(slide_path, slide_dur, zoom_in=(i % 2 == 0))
        if i > 0:
            clip = clip.with_effects([CrossFadeIn(CROSSFADE)])
        clip = clip.with_start(cursor)
        visual_clips.append(clip)

        # Voice starts at cursor+head; subsequent slides nudge into the crossfade
        audio_start = cursor + head + (CROSSFADE / 2 if i > 0 else 0)
        audio_clips.append(voice.with_start(audio_start))

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

    book_title = content.get("book", "")
    book_author = content.get("author", "")

    slide_paths = []
    for i, slide in enumerate(slides):
        path = slides_dir / f"{i + 1:02d}.png"
        # Inject book metadata into CTA so the renderer can display it
        if slide.get("type") == "cta":
            slide["_book"] = book_title
            slide["_author"] = book_author
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

"""Reusable background themes for any book reel.

Each theme returns a 1080x1920 RGB image keyed by an accent color.
Themes are intentionally generic — picked per slide by the LLM.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920


# ----------------------------- accent palettes -----------------------------


PALETTES = {
    "gold":   {"base_top": (40, 60, 100), "base_bot": (8, 15, 35), "accent": (255, 215, 100), "soft": (255, 200, 130)},
    "red":    {"base_top": (110, 30, 40), "base_bot": (30, 8, 15), "accent": (255, 100, 100), "soft": (255, 150, 150)},
    "green":  {"base_top": (25, 90, 65), "base_bot": (8, 30, 22), "accent": (120, 240, 160), "soft": (160, 240, 180)},
    "blue":   {"base_top": (30, 70, 130), "base_bot": (8, 18, 50), "accent": (110, 180, 255), "soft": (160, 200, 255)},
    "purple": {"base_top": (65, 30, 110), "base_bot": (20, 8, 45), "accent": (200, 130, 255), "soft": (220, 170, 255)},
}


def _palette(accent_color: str) -> dict:
    return PALETTES.get(accent_color, PALETTES["gold"])


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates_bold = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
    candidates_reg = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    for name in (candidates_bold if bold else candidates_reg):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ----------------------------- primitives -----------------------------


def _vertical_gradient(top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    return img


def _radial_glow(img: Image.Image, center: tuple, color: tuple, radius: int, strength: float = 0.5) -> Image.Image:
    overlay = Image.new("RGB", (W, H), color)
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    cx, cy = center
    for i in range(60):
        r = radius * (1 - i / 60)
        alpha = int(strength * 255 * (i / 60))
        md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(60))
    return Image.composite(overlay, img, mask)


def _corner_vignette(img: Image.Image, strength: int = 130) -> Image.Image:
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    cx, cy = W // 2, H // 2
    max_r = math.hypot(cx, cy)
    for i in range(35):
        r = max_r * (1 - i / 35)
        alpha = int((i / 35) * strength)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)
    mask = mask.filter(ImageFilter.GaussianBlur(80))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(dark, img, mask)


def _light_rays(img: Image.Image, center: tuple, color: tuple, n_rays: int = 16, length: int = 1400, alpha: int = 60) -> Image.Image:
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cx, cy = center
    for i in range(n_rays):
        ang = (i / n_rays) * 360
        rad = math.radians(ang)
        x2 = cx + math.cos(rad) * length
        y2 = cy + math.sin(rad) * length
        od.line([(cx, cy), (x2, y2)], fill=(*color, alpha), width=8)
    overlay = overlay.filter(ImageFilter.GaussianBlur(4))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# ----------------------------- themes -----------------------------


def hero_word(accent_color: str, theme_word: str) -> Image.Image:
    """Massive single character/symbol behind the text."""
    p = _palette(accent_color)
    img = _vertical_gradient(p["base_top"], p["base_bot"])
    img = _radial_glow(img, (W // 2, H // 2), p["soft"], 1100, strength=0.5)
    img = _light_rays(img, (W // 2, H // 2), p["accent"], n_rays=18, length=1500, alpha=45)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    word = (theme_word or "$")[:3]  # cap to avoid blow-out
    target_size = 1500 if len(word) == 1 else (900 if len(word) == 2 else 600)
    f = _font(target_size, bold=True)
    bbox = od.textbbox((0, 0), word, font=f)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    od.text(((W - tw) // 2 - bbox[0], H // 2 - th // 2 - bbox[1] - 80), word, font=f, fill=(*p["accent"], 60))
    overlay = overlay.filter(ImageFilter.GaussianBlur(2))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return _corner_vignette(img, strength=140)


def split(accent_color: str, theme_word: str = "") -> Image.Image:
    """Diagonal split — cool slate vs warm accent. Good for contrasts."""
    p = _palette(accent_color)
    img = Image.new("RGB", (W, H), (0, 0, 0))
    px = img.load()
    cool_top = (95, 110, 140)
    cool_bot = (45, 55, 80)
    warm_top = p["base_top"]
    warm_bot = p["base_bot"]
    for y in range(H):
        for x in range(W):
            below_diag = (x / W + y / H) > 1.0
            t = y / H
            if not below_diag:
                r = int(cool_top[0] * (1 - t) + cool_bot[0] * t)
                g = int(cool_top[1] * (1 - t) + cool_bot[1] * t)
                b = int(cool_top[2] * (1 - t) + cool_bot[2] * t)
            else:
                r = int(warm_top[0] * (1 - t) + warm_bot[0] * t)
                g = int(warm_top[1] * (1 - t) + warm_bot[1] * t)
                b = int(warm_top[2] * (1 - t) + warm_bot[2] * t)
            px[x, y] = (r, g, b)
    d = ImageDraw.Draw(img)
    d.line([(W, 0), (0, H)], fill=p["accent"], width=6)
    return _corner_vignette(img, strength=100)


def rising(accent_color: str, theme_word: str = "") -> Image.Image:
    """Bold rising chart with grid + skyline. For growth/success."""
    p = _palette(accent_color)
    img = _vertical_gradient(p["base_top"], p["base_bot"])
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(0, H, 160):
        od.line([(0, y), (W, y)], fill=(255, 255, 255, 22), width=2)
    for x in range(0, W, 180):
        od.line([(x, 0), (x, H)], fill=(255, 255, 255, 22), width=2)

    rng = random.Random(7)
    n = 28
    base_y = H - 350
    top_y = 280
    points = []
    for i in range(n + 1):
        x = int(i / n * W)
        progress = i / n
        y = int(base_y - progress * (base_y - top_y) + rng.randint(-50, 50))
        points.append((x, y))
    poly = points + [(W, H), (0, H)]
    od.polygon(poly, fill=(*p["accent"], 60))
    for i in range(len(points) - 1):
        od.line([points[i], points[i + 1]], fill=(*p["accent"], 230), width=14)
    last = points[-1]
    od.polygon(
        [(last[0] - 50, last[1] + 50), (last[0] + 50, last[1] + 50), (last[0], last[1] - 50)],
        fill=(*p["accent"], 240),
    )

    rng2 = random.Random(99)
    x = 0
    while x < W:
        bw = rng2.randint(70, 160)
        bh = rng2.randint(120, 320)
        od.rectangle([x, H - bh, x + bw, H], fill=(15, 30, 25, 230))
        for wy in range(H - bh + 20, H - 20, 35):
            for wx in range(x + 12, x + bw - 12, 25):
                if rng2.random() > 0.5:
                    od.rectangle([wx, wy, wx + 10, wy + 18], fill=(255, 220, 130, 200))
        x += bw + 4

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return _corner_vignette(img, strength=110)


def rays(accent_color: str, theme_word: str = "") -> Image.Image:
    """Radial light burst with floating particles. For revelation/insight."""
    p = _palette(accent_color)
    img = _vertical_gradient(p["base_top"], p["base_bot"])
    img = _radial_glow(img, (W // 2, H // 2), p["soft"], 1000, strength=0.6)
    img = _light_rays(img, (W // 2, H // 2), p["accent"], n_rays=24, length=1600, alpha=60)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    rng = random.Random(3)
    for _ in range(70):
        px_ = rng.randint(0, W)
        py_ = rng.randint(0, H)
        size = rng.randint(4, 14)
        alpha = rng.randint(120, 220)
        od.ellipse([px_ - size, py_ - size, px_ + size, py_ + size], fill=(*p["accent"], alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return _corner_vignette(img, strength=80)


def rings(accent_color: str, theme_word: str = "") -> Image.Image:
    """Concentric rings with a curved arrow. For loops/cycles/traps."""
    p = _palette(accent_color)
    img = _vertical_gradient(p["base_top"], p["base_bot"])
    img = _radial_glow(img, (W // 2, H // 2), p["soft"], 700, strength=0.35)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cx, cy = W // 2, H // 2
    R = 720
    od.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(*p["accent"], 200), width=14)
    od.ellipse([cx - R + 80, cy - R + 80, cx + R - 80, cy + R - 80], outline=(*p["accent"], 130), width=6)
    for i in range(24):
        ang = (i / 24) * 360
        rad = math.radians(ang)
        x1 = cx + math.cos(rad) * 90
        y1 = cy + math.sin(rad) * 90
        x2 = cx + math.cos(rad) * (R - 14)
        y2 = cy + math.sin(rad) * (R - 14)
        od.line([(x1, y1), (x2, y2)], fill=(*p["accent"], 100), width=4)
    od.ellipse([cx - 70, cy - 70, cx + 70, cy + 70], fill=(*p["accent"], 200))
    od.arc([cx - R - 80, cy - R - 80, cx + R + 80, cy + R + 80], start=200, end=340, fill=(255, 100, 100, 200), width=14)
    end_ang = math.radians(340)
    ex = cx + math.cos(end_ang) * (R + 80)
    ey = cy + math.sin(end_ang) * (R + 80)
    od.polygon(
        [(ex - 30, ey - 40), (ex + 50, ey + 10), (ex - 10, ey + 40)],
        fill=(255, 100, 100, 230),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return _corner_vignette(img, strength=130)


def silhouette(accent_color: str, theme_word: str = "") -> Image.Image:
    """A large dark glowing orb behind text. Generic 'archetypal object'."""
    p = _palette(accent_color)
    img = _vertical_gradient(p["base_top"], p["base_bot"])
    img = _radial_glow(img, (W // 2, H // 2 - 100), p["soft"], 900, strength=0.65)
    img = _light_rays(img, (W // 2, H // 2 - 100), p["accent"], n_rays=20, length=1400, alpha=55)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cx, cy = W // 2, H // 2 - 80
    R = 380
    od.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(20, 15, 30, 220), outline=(*p["accent"], 230), width=8)

    if theme_word:
        f = _font(220, bold=True)
        word = theme_word[:3]
        bbox = od.textbbox((0, 0), word, font=f)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        od.text((cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1]), word, font=f, fill=(*p["accent"], 220))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return _corner_vignette(img, strength=100)


THEMES = {
    "hero_word": hero_word,
    "split": split,
    "rising": rising,
    "rays": rays,
    "rings": rings,
    "silhouette": silhouette,
}


def render_background(theme: str, accent_color: str, theme_word: str = "") -> Image.Image:
    fn = THEMES.get(theme, rays)  # rays is a safe default
    return fn(accent_color, theme_word)

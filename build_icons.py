"""
Generate Auralis icons.

Outputs:
  assets/auralis.ico            Multi-resolution Windows icon (16, 24, 32, 48, 64, 128, 256)
  assets/auralis.png            512×512 master
  assets/tile_44.png  71.png  150.png  310x150.png  310.png   Store tiles
  assets/splash.png             620×300 splash screen

Run:  py -3 build_icons.py
(Uses Pillow, already a transitive dep via ttkbootstrap.)
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

ACCENT = (59, 130, 246, 255)
WHITE  = (255, 255, 255, 255)


def draw_logo(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * 0.22)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=ACCENT)
    bar_w = max(2, int(size * 0.07))
    gap = max(2, int(size * 0.09))
    heights = [0.35, 0.60, 0.85, 0.60, 0.35]
    total_w = len(heights) * bar_w + (len(heights) - 1) * gap
    cx, cy = size / 2, size / 2
    x = int(cx - total_w / 2)
    bar_radius = max(1, bar_w // 2)
    for h in heights:
        half = (size * h) / 2
        draw.rounded_rectangle(
            (x, int(cy - half), x + bar_w, int(cy + half)),
            radius=bar_radius, fill=WHITE,
        )
        x += bar_w + gap
    return img


def draw_tile(width: int, height: int, scale_logo: float = 0.65) -> Image.Image:
    img = Image.new("RGBA", (width, height), ACCENT)
    logo_size = int(min(width, height) * scale_logo)
    logo = draw_logo(logo_size)
    px = (width - logo_size) // 2
    py = (height - logo_size) // 2
    img.alpha_composite(logo, (px, py))
    return img


def write_master():
    p = ASSETS / "auralis.png"
    draw_logo(512).save(p)
    print("wrote", p)


def write_ico():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [draw_logo(s) for s in sizes]
    p = ASSETS / "auralis.ico"
    images[0].save(p, format="ICO", sizes=[(s, s) for s in sizes])
    print("wrote", p, "(", ", ".join(str(s) for s in sizes), ")")


def write_tiles():
    targets = [
        ("tile_44.png",      44, 44),
        ("tile_71.png",      71, 71),
        ("tile_150.png",    150, 150),
        ("tile_310x150.png",310, 150),
        ("tile_310.png",    310, 310),
    ]
    for name, w, h in targets:
        p = ASSETS / name
        draw_tile(w, h).save(p)
        print("wrote", p)


def write_splash():
    img = draw_tile(620, 300, scale_logo=0.50)
    try:
        from PIL import ImageFont
        font = None
        for cand in ("seguisb.ttf", "segoeui.ttf", "Arial.ttf"):
            try:
                font = ImageFont.truetype(cand, 42)
                break
            except Exception:
                continue
        if font is not None:
            draw = ImageDraw.Draw(img)
            text = "Auralis"
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((620 - tw - 28, 130), text, font=font, fill=WHITE)
    except Exception:
        pass
    p = ASSETS / "splash.png"
    img.save(p)
    print("wrote", p)


if __name__ == "__main__":
    write_master()
    write_ico()
    write_tiles()
    write_splash()
    print("\nAll icons written to:", ASSETS)

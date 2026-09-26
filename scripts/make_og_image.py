"""Генерирует app/static/img/og-default.jpg — превью ссылки на сайт в мессенджерах.
Запуск: python scripts/make_og_image.py (нужен шрифт с кириллицей, путь можно передать аргументом)."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import BASE_DIR, settings  # noqa: E402

FONT_CANDIDATES = [
    *sys.argv[1:],
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("Не найден шрифт с кириллицей — передайте путь к .ttf аргументом")


img = Image.new("RGB", (1200, 630), (31, 74, 63))
d = ImageDraw.Draw(img)
d.rounded_rectangle([80, 80, 176, 176], radius=24, fill=(255, 255, 255))
d.polygon([(104, 132), (128, 108), (152, 132), (152, 158), (104, 158)], fill=(31, 74, 63))
d.text((80, 250), settings.realtor_name, font=font(76), fill=(255, 255, 255))
d.text((80, 350), f"{settings.realtor_title} · {settings.city}", font=font(40), fill=(214, 228, 222))
d.text((80, 470), "Покупка · продажа · аренда · сопровождение сделок", font=font(32), fill=(214, 186, 150))
out = BASE_DIR / "app" / "static" / "img" / "og-default.jpg"
img.save(out, "JPEG", quality=88, optimize=True)
print(out)

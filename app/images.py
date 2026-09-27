"""Обработка фото объектов: поворот по EXIF, удаление метаданных (в т.ч. GPS), WebP в двух размерах + JPEG для превью в мессенджерах."""

import secrets
import shutil
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from app.config import settings

register_heif_opener()  # фото с iPhone в формате HEIC/HEIF открываются как обычные картинки

WEBP_SIZES = {"thumb": 800, "full": 1920}  # максимальная сторона, px
WEBP_QUALITY = 80
OG_SIZE = (1200, 630)  # стандарт Open Graph; мессенджеры плохо дружат с WebP, поэтому JPEG


def property_dir(property_id: int) -> Path:
    return settings.media_dir / "properties" / str(property_id)


def save_photo(property_id: int, data: bytes) -> str:
    """Сохраняет фото, возвращает базовое имя файлов. Бросает PIL.UnidentifiedImageError для не-картинок."""
    img = Image.open(BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")  # convert отбрасывает EXIF

    name = secrets.token_hex(6)
    target = property_dir(property_id)
    target.mkdir(parents=True, exist_ok=True)

    for size, max_side in WEBP_SIZES.items():
        resized = img.copy()
        resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        resized.save(target / f"{name}_{size}.webp", "WEBP", quality=WEBP_QUALITY, method=4)

    og = ImageOps.fit(img, OG_SIZE, Image.Resampling.LANCZOS)
    og.save(target / f"{name}_og.jpg", "JPEG", quality=82, optimize=True, progressive=True)
    return name


PROFILE_MAX_SIDE = 1200


def save_profile_photo(data: bytes) -> str:
    """Фото риелтора для сайта: WebP до 1200px. Возвращает имя файла в media/profile/."""
    img = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
    img.thumbnail((PROFILE_MAX_SIDE, PROFILE_MAX_SIDE), Image.Resampling.LANCZOS)
    target = settings.media_dir / "profile"
    target.mkdir(parents=True, exist_ok=True)
    name = f"realtor_{secrets.token_hex(6)}.webp"
    img.save(target / name, "WEBP", quality=85, method=4)
    return name


def delete_profile_photo(name: str | None) -> None:
    if name:
        (settings.media_dir / "profile" / name).unlink(missing_ok=True)


def delete_photo_files(property_id: int, name: str) -> None:
    for f in property_dir(property_id).glob(f"{name}_*"):
        f.unlink(missing_ok=True)


def delete_property_files(property_id: int) -> None:
    shutil.rmtree(property_dir(property_id), ignore_errors=True)

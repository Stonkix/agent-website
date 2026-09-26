"""Демо-данные для локальной разработки: python seed.py  (повторный запуск очищает объекты, заявки и отзывы)."""

import random
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image, ImageDraw
from sqlalchemy import delete, select

from app import images
from app.db import Base, SessionLocal, engine
from app.models import Lead, Photo, Property, Review

random.seed(7)

PALETTES = [
    [(236, 229, 216), (196, 176, 150), (120, 98, 74)],
    [(226, 234, 236), (170, 190, 196), (70, 96, 104)],
    [(240, 236, 228), (210, 196, 172), (150, 122, 90)],
    [(232, 236, 226), (182, 196, 168), (88, 110, 76)],
]


def fake_photo(i: int) -> bytes:
    """Условная «комната»: стена, пол, окно — чтобы галерея выглядела живо без реальных фото."""
    wall, floor, dark = random.choice(PALETTES)
    img = Image.new("RGB", (1600, 1200), wall)
    d = ImageDraw.Draw(img)
    d.polygon([(0, 820), (1600, 820), (1600, 1200), (0, 1200)], fill=floor)
    wx = random.randint(150, 900)
    d.rectangle([wx, 220, wx + 520, 700], fill=(250, 252, 255), outline=dark, width=14)
    d.line([wx + 260, 220, wx + 260, 700], fill=dark, width=10)
    d.rectangle([1100, 560, 1480, 830], fill=dark)
    d.text((40, 40), f"Демо-фото {i + 1}", fill=dark)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


OBJECTS = [
    dict(title="2-комн. квартира у парка Горького", deal_type="sale", property_type="flat", price=8_900_000, old_price=9_400_000,
         rooms=2, area_total=58.4, area_living=32, area_kitchen=11.5, floor=7, floors_total=16, year_built=2016, house_type="Монолит",
         district="Советский", address="ул. Николая Ершова, 55", lat=55.7899, lon=49.1741, tags="Ипотека, Свободная продажа", is_featured=True),
    dict(title="Студия в новостройке рядом с метро", deal_type="sale", property_type="flat", price=5_350_000,
         rooms=0, area_total=27.1, area_kitchen=None, floor=12, floors_total=22, year_built=2023, house_type="Монолит",
         district="Ново-Савиновский", address="пр. Ямашева, 97", lat=55.8263, lon=49.1244, tags="Новостройка, Ипотека от 6%", is_featured=True),
    dict(title="3-комн. квартира в историческом центре", deal_type="sale", property_type="flat", price=16_700_000,
         rooms=3, area_total=94, area_living=61, area_kitchen=14, floor=3, floors_total=5, year_built=1956, house_type="Кирпич",
         district="Вахитовский", address="ул. Карла Маркса, 42", lat=55.7955, lon=49.1310, tags="Высокие потолки", is_featured=True),
    dict(title="Дом с участком 8 соток", deal_type="sale", property_type="house", price=12_500_000,
         rooms=4, area_total=146, floor=None, floors_total=2, year_built=2019, house_type="Газобетон",
         district="Приволжский", address="пос. Салмачи, ул. Садовая, 14", lat=55.7382, lon=49.2011, tags="Газ, Баня", is_featured=True),
    dict(title="1-комн. квартира с ремонтом", deal_type="sale", property_type="flat", price=6_200_000,
         rooms=1, area_total=38.5, area_living=18, area_kitchen=9, floor=5, floors_total=9, year_built=2008, house_type="Панель",
         district="Приволжский", address="ул. Рихарда Зорге, 66", lat=55.7571, lon=49.1886, tags="С мебелью"),
    dict(title="2-комн. квартира в аренду на длительный срок", deal_type="rent", property_type="flat", price=45_000, status="for_rent",
         rooms=2, area_total=52, area_kitchen=10, floor=4, floors_total=10, year_built=2012, house_type="Кирпич",
         district="Советский", address="ул. Академика Сахарова, 21", lat=55.7870, lon=49.1965, tags="Можно с детьми", is_featured=True),
    dict(title="Студия в аренду у КФУ", deal_type="rent", property_type="flat", price=28_000, status="rented",
         rooms=0, area_total=24, floor=2, floors_total=9, year_built=2015, house_type="Монолит",
         district="Вахитовский", address="ул. Пушкина, 34", lat=55.7932, lon=49.1265),
    dict(title="Участок 10 соток под ИЖС", deal_type="sale", property_type="land", price=2_400_000,
         area_total=1000, district="Кировский", address="с. Нижние Верхосунья, ул. Лесная", lat=55.8400, lon=48.9800, tags="Электричество"),
    dict(title="3-комн. квартира для семьи", deal_type="sale", property_type="flat", price=10_300_000, status="sold",
         rooms=3, area_total=74, area_living=45, area_kitchen=12, floor=6, floors_total=10, year_built=2014, house_type="Кирпич",
         district="Ново-Савиновский", address="ул. Чистопольская, 71", lat=55.8215, lon=49.1320),
    dict(title="Офис на первой линии", deal_type="sale", property_type="commercial", price=14_900_000,
         area_total=86, floor=1, floors_total=9, district="Вахитовский", address="ул. Баумана, 19", lat=55.7887, lon=49.1197,
         tags="Отдельный вход"),
]

DESCRIPTION = (
    "Светлая квартира с продуманной планировкой: комнаты изолированы, окна на две стороны.\n\n"
    "Во дворе детская и спортивная площадки, закрытая территория. В шаговой доступности школа, "
    "детский сад, супермаркеты и остановки общественного транспорта.\n\n"
    "Один взрослый собственник, более 5 лет в собственности. Подходит под ипотеку."
)

REVIEWS = [
    ("Марина и Алексей", "Продажа 2-комн. + покупка 3-комн.", "Провели альтернативную сделку за полтора месяца. Всё чётко по срокам, документы проверены до мелочей, в банке и МФЦ всё сопровождали."),
    ("Ильдар", "Покупка студии в ипотеку", "Нашла вариант, которого не было на Авито, и выторговала 250 тысяч. Отдельное спасибо за помощь с одобрением ипотеки."),
    ("Светлана Петровна", "Продажа квартиры", "Боялась продавать сама — наследство, много документов. Всё объяснили простыми словами и продали быстрее, чем я ожидала."),
]


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for prop_id in db.scalars(select(Property.id)):
            images.delete_property_files(prop_id)
        db.execute(delete(Lead))
        db.execute(delete(Photo))
        db.execute(delete(Property))
        db.execute(delete(Review))

        for i, data in enumerate(OBJECTS):
            p = Property(description=DESCRIPTION, **data)
            p.created_at = datetime.now() - timedelta(days=i * 4)
            db.add(p)
            db.flush()
            for n in range(random.randint(3, 7)):
                db.add(Photo(property_id=p.id, name=images.save_photo(p.id, fake_photo(n)), sort=n))

        for author, deal, text in REVIEWS:
            db.add(Review(author=author, deal=deal, text=text))
        db.commit()
    print(f"Готово: {len(OBJECTS)} объектов, {len(REVIEWS)} отзыва.")


if __name__ == "__main__":
    main()

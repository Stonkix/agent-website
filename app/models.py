from datetime import datetime, timedelta

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils import fmt_num

DEAL_TYPES = {"sale": "Продажа", "rent": "Аренда"}
PROPERTY_TYPES = {
    "flat": "Квартира",
    "house": "Дом",
    "land": "Участок",
    "commercial": "Коммерческая",
}
STATUSES = {"active": "В продаже", "for_rent": "Сдается", "sold": "Продано", "rented": "Сдан"}
CLOSED_STATUSES = ("sold", "rented")  # сделка закрыта: не в каталоге, показываются в «Недавних сделках»
_RENT_STATUS = {"active": "for_rent", "sold": "rented"}
_SALE_STATUS = {v: k for k, v in _RENT_STATUS.items()}

LEAD_KINDS = {
    "callback": "Обратный звонок",
    "viewing": "Запись на просмотр",
    "valuation": "Оценка квартиры",
    "question": "Вопрос",
}

NEW_BADGE_DAYS = 14


def status_for_deal(deal_type: str, status: str) -> str:
    """Приводит статус к типу сделки: у аренды «Сдается/Сдан», у продажи «В продаже/Продано»."""
    mapping = _RENT_STATUS if deal_type == "rent" else _SALE_STATUS
    return mapping.get(status, status)


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    deal_type: Mapped[str] = mapped_column(String(20), default="sale", index=True)
    property_type: Mapped[str] = mapped_column(String(20), default="flat", index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)

    price: Mapped[int] = mapped_column(index=True)
    old_price: Mapped[int | None] = mapped_column(default=None)  # заполнено → «Снижена цена»

    rooms: Mapped[int | None] = mapped_column(default=None, index=True)  # 0 — студия
    area_total: Mapped[float | None] = mapped_column(Float, default=None)
    area_living: Mapped[float | None] = mapped_column(Float, default=None)
    area_kitchen: Mapped[float | None] = mapped_column(Float, default=None)
    floor: Mapped[int | None] = mapped_column(default=None)
    floors_total: Mapped[int | None] = mapped_column(default=None)
    year_built: Mapped[int | None] = mapped_column(default=None)
    house_type: Mapped[str | None] = mapped_column(String(50), default=None)

    district: Mapped[str | None] = mapped_column(String(100), default=None, index=True)
    address: Mapped[str] = mapped_column(String(250), default="")
    lat: Mapped[float | None] = mapped_column(Float, default=None)
    lon: Mapped[float | None] = mapped_column(Float, default=None)

    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str | None] = mapped_column(String(250), default=None)  # через запятую
    is_featured: Mapped[bool] = mapped_column(default=False)  # показывать на главной
    is_published: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    photos: Mapped[list["Photo"]] = relationship(
        back_populates="listing",
        order_by="Photo.sort",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Поле загрузки фото в админке не хранится в БД; атрибут нужен sqladmin при редактировании
    photos_upload = None

    def __str__(self) -> str:
        return f"#{self.id} {self.title}"

    @property
    def url(self) -> str:
        return f"/catalog/{self.id}"

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    @property
    def cover(self) -> "Photo | None":
        return self.photos[0] if self.photos else None

    @property
    def price_per_m2(self) -> int | None:
        if self.area_total and self.deal_type == "sale":
            return round(self.price / self.area_total)
        return None

    @property
    def rooms_label(self) -> str:
        if self.rooms is None:
            return ""
        return "Студия" if self.rooms == 0 else f"{self.rooms}-комн."

    @property
    def is_new(self) -> bool:
        return self.created_at is not None and datetime.now() - self.created_at < timedelta(
            days=NEW_BADGE_DAYS
        )

    @property
    def price_reduced(self) -> bool:
        return bool(self.old_price and self.old_price > self.price)

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def short_title(self) -> str:
        """«2-комн. квартира, 54 м²» — для заголовков, OG и писем о заявках."""
        parts = []
        if self.property_type == "flat" and self.rooms is not None:
            parts.append("Квартира-студия" if self.rooms == 0 else f"{self.rooms}-комн. квартира")
        else:
            parts.append(PROPERTY_TYPES.get(self.property_type, ""))
        if self.area_total:
            parts.append(f"{fmt_num(self.area_total)} м²")
        return ", ".join(p for p in parts if p)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))  # базовое имя файлов без суффикса
    sort: Mapped[int] = mapped_column(default=0)

    listing: Mapped[Property] = relationship(back_populates="photos")

    def __str__(self) -> str:
        return f"Фото {self.name}"

    def _url(self, size: str, ext: str = "webp") -> str:
        return f"/media/properties/{self.property_id}/{self.name}_{size}.{ext}"

    @property
    def thumb(self) -> str:
        return self._url("thumb")

    @property
    def full(self) -> str:
        return self._url("full")

    @property
    def og(self) -> str:
        return self._url("og", "jpg")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="callback")
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text, default="")
    property_id: Mapped[int | None] = mapped_column(
        ForeignKey("properties.id", ondelete="SET NULL"), default=None
    )
    is_processed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    listing: Mapped[Property | None] = relationship()

    def __str__(self) -> str:
        return f"{self.name} {self.phone}"


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    author: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    deal: Mapped[str | None] = mapped_column(String(150), default=None)  # «Продажа 2-комн. в Советском р-не»
    is_published: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    def __str__(self) -> str:
        return self.author


DEFAULT_ABOUT = (
    "Работаю с недвижимостью в г. Калуга 13 лет. Веду сделку лично от первого звонка до передачи ключей "
    "— без стажёров и «передачи дел».\n\n"
    "Специализируюсь на вторичном рынке и новостройках, сделках с ипотекой, маткапиталом "
    "и альтернативных сделках. Состою в гильдии риелторов, ответственность застрахована."
)


class Profile(Base):
    """Портфолио риелтора — одна строка (id=1), редактируется в админке «Настройка Портфолио»."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo: Mapped[str | None] = mapped_column(String(64), default=None)  # файл в media/profile/
    about: Mapped[str] = mapped_column(Text, default=DEFAULT_ABOUT)
    years_experience: Mapped[int] = mapped_column(default=13)
    deals_closed: Mapped[int] = mapped_column(default=300)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    @property
    def photo_url(self) -> str:
        return f"/media/profile/{self.photo}" if self.photo else "/static/img/realtor.svg"

    @property
    def paragraphs(self) -> list[str]:
        return [p.strip() for p in self.about.split("\n\n") if p.strip()]


class LoginAttempt(Base):
    """Неудачные попытки входа в админку по IP (см. app/login_guard.py)."""

    __tablename__ = "login_attempts"

    ip: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(default=0)
    last_failure_at: Mapped[datetime | None] = mapped_column(default=None)
    blocked_until: Mapped[datetime | None] = mapped_column(default=None)


class AdminCredential(Base):
    """Хеш пароля панели управления после смены в разделе «Смена пароля» (см. app/admin_password.py)."""

    __tablename__ = "admin_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

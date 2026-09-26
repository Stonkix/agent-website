import math
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import CLOSED_STATUSES, DEAL_TYPES, PROPERTY_TYPES, Property, Review
from app.templating import templates

router = APIRouter()

PAGE_SIZE = 12
SORTS = {
    "new": ("Сначала новые", Property.created_at.desc()),
    "price_asc": ("Сначала дешевле", Property.price.asc()),
    "price_desc": ("Сначала дороже", Property.price.desc()),
    "area_desc": ("По площади", Property.area_total.desc()),
}
ROOM_OPTIONS = [(0, "Студия"), (1, "1"), (2, "2"), (3, "3"), (4, "4+")]


def published():
    return select(Property).where(Property.is_published.is_(True))


def _int(value: str | None) -> int | None:
    try:
        return int(re.sub(r"\s", "", value or ""))
    except ValueError:
        return None


@dataclass
class CatalogFilters:
    deal: str = "sale"
    type: str = ""
    rooms: list[int] = field(default_factory=list)
    price_min: int | None = None
    price_max: int | None = None
    district: str = ""
    sort: str = "new"
    page: int = 1

    @classmethod
    def from_request(cls, request: Request) -> "CatalogFilters":
        qp = request.query_params
        deal = qp.get("deal", "sale")
        ptype = qp.get("type", "")
        sort = qp.get("sort", "new")
        return cls(
            deal=deal if deal in DEAL_TYPES else "sale",
            type=ptype if ptype in PROPERTY_TYPES else "",
            rooms=sorted({r for r in map(_int, qp.getlist("rooms")) if r is not None and 0 <= r <= 4}),
            price_min=_int(qp.get("price_min")),
            price_max=_int(qp.get("price_max")),
            district=qp.get("district", "")[:100],
            sort=sort if sort in SORTS else "new",
            page=max(_int(qp.get("page")) or 1, 1),
        )

    def apply(self, q):
        q = q.where(Property.status.not_in(CLOSED_STATUSES), Property.deal_type == self.deal)
        if self.type:
            q = q.where(Property.property_type == self.type)
        if self.rooms:
            conds = [Property.rooms == r for r in self.rooms if r < 4]
            if 4 in self.rooms:
                conds.append(Property.rooms >= 4)
            q = q.where(or_(*conds))
        if self.price_min:
            q = q.where(Property.price >= self.price_min)
        if self.price_max:
            q = q.where(Property.price <= self.price_max)
        if self.district:
            q = q.where(Property.district == self.district)
        return q

    def query_string(self, **override) -> str:
        params = {
            "deal": self.deal,
            "type": self.type,
            "rooms": self.rooms,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "district": self.district,
            "sort": self.sort if self.sort != "new" else None,
            "page": self.page if self.page > 1 else None,
        } | override
        return urlencode({k: v for k, v in params.items() if v not in (None, "", [])}, doseq=True)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    # на главной только объекты с галочкой «На главную»; нет таких — блок не выводится
    featured = db.scalars(
        published()
        .where(Property.is_featured.is_(True), Property.status.not_in(CLOSED_STATUSES))
        .order_by(Property.created_at.desc())
        .limit(6)
    ).all()
    reviews = db.scalars(
        select(Review).where(Review.is_published.is_(True)).order_by(Review.created_at.desc()).limit(3)
    ).all()
    return templates.TemplateResponse(
        request, "index.html", {"featured": featured, "reviews": reviews}
    )


def _districts(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(Property.district)
            .distinct()
            .where(Property.is_published.is_(True), Property.district.is_not(None), Property.district != "")
            .order_by(Property.district)
        )
    )


@router.get("/catalog", response_class=HTMLResponse)
def catalog(request: Request, db: Session = Depends(get_db)):
    f = CatalogFilters.from_request(request)
    q = f.apply(published())
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    pages = max(math.ceil(total / PAGE_SIZE), 1)
    f.page = min(f.page, pages)
    items = db.scalars(
        q.order_by(SORTS[f.sort][1], Property.id.desc()).limit(PAGE_SIZE).offset((f.page - 1) * PAGE_SIZE)
    ).all()

    ctx = {
        "f": f,
        "items": items,
        "total": total,
        "pages": pages,
        "sorts": SORTS,
        "room_options": ROOM_OPTIONS,
        "districts": _districts(db),
    }
    # HTMX-запрос от фильтров: отдаём только сетку, без шапки и фильтров
    is_htmx = request.headers.get("HX-Request") == "true" and not request.headers.get("HX-History-Restore-Request")
    template = "partials/catalog_results.html" if is_htmx else "catalog.html"
    response = templates.TemplateResponse(request, template, ctx)
    response.headers["Vary"] = "HX-Request"
    return response


@router.get("/catalog/{ref}", response_class=HTMLResponse)
def property_detail(ref: str, request: Request, db: Session = Depends(get_db)):
    prop_id = _int(ref.split("-", 1)[0])
    prop = db.get(Property, prop_id) if prop_id else None
    if not prop or not prop.is_published:
        raise HTTPException(404)
    if request.url.path != prop.url:  # один URL на объект для SEO (старые адреса вида /catalog/1-slug)
        return RedirectResponse(prop.url, status_code=301)

    similar = db.scalars(
        published()
        .where(
            Property.id != prop.id,
            Property.status.not_in(CLOSED_STATUSES),
            Property.deal_type == prop.deal_type,
            Property.property_type == prop.property_type,
            Property.price.between(prop.price * 0.7, prop.price * 1.3),
        )
        .order_by(func.abs(Property.price - prop.price))
        .limit(3)
    ).all()
    return templates.TemplateResponse(
        request,
        "property.html",
        {"p": prop, "similar": similar, "json_ld": _listing_json_ld(prop)},
    )


def _listing_json_ld(p: Property) -> dict:
    url = settings.base_url + p.url
    place_type = {"flat": "Apartment", "house": "SingleFamilyResidence"}.get(p.property_type, "Place")
    about: dict = {
        "@type": place_type,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": p.address,
            "addressLocality": settings.city,
            "addressCountry": "RU",
        },
    }
    if p.rooms is not None and place_type != "Place":
        about["numberOfRooms"] = max(p.rooms, 1)
    if p.area_total and place_type != "Place":
        about["floorSize"] = {"@type": "QuantitativeValue", "value": p.area_total, "unitCode": "MTK"}
    if p.lat and p.lon:
        about["geo"] = {"@type": "GeoCoordinates", "latitude": p.lat, "longitude": p.lon}
    return {
        "@context": "https://schema.org",
        "@type": "RealEstateListing",
        "name": f"{p.short_title} — {p.address}",
        "url": url,
        "description": p.description[:500],
        "datePosted": p.created_at.date().isoformat(),
        "image": [settings.base_url + ph.full for ph in p.photos[:5]],
        "about": about,
        "offers": {
            "@type": "Offer",
            "price": p.price,
            "priceCurrency": "RUB",
            "availability": "https://schema.org/SoldOut" if p.is_closed else "https://schema.org/InStock",
            "url": url,
        },
    }


@router.get("/about", response_class=HTMLResponse)
def about(request: Request, db: Session = Depends(get_db)):
    reviews = db.scalars(
        select(Review).where(Review.is_published.is_(True)).order_by(Review.created_at.desc())
    ).all()
    sold = db.scalars(
        published().where(Property.status.in_(CLOSED_STATUSES)).order_by(Property.updated_at.desc()).limit(6)
    ).all()
    return templates.TemplateResponse(request, "about.html", {"reviews": reviews, "sold": sold})


@router.get("/contacts", response_class=HTMLResponse)
def contacts(request: Request):
    return templates.TemplateResponse(request, "contacts.html")


@router.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html")


@router.get("/thanks", response_class=HTMLResponse)
def thanks(request: Request):
    return templates.TemplateResponse(request, "thanks.html")

import os
import tempfile
from io import BytesIO

_tmp = tempfile.mkdtemp()
os.environ.update(
    DEBUG="true",
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    MEDIA_DIR=f"{_tmp}/media",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import images  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Lead, Photo, Property  # noqa: E402
from app.models import status_for_deal  # noqa: E402
from app.utils import normalize_phone  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        with SessionLocal() as db:
            p = Property(title="2-комн. квартира", price=5_000_000,
                         rooms=2, area_total=50, address="ул. Тестовая, 1", district="Центр")
            db.add(p)
            db.add(Property(title="Продано", price=3_000_000, status="sold", address="x"))
            db.add(Property(title="Сдана", deal_type="rent", price=30_000, status="rented", address="x"))
            db.add(Property(title="Скрыт", price=3_000_000, is_published=False, address="x"))
            db.commit()
            buf = BytesIO()
            Image.new("RGB", (3000, 2000), "red").save(buf, "JPEG")
            db.add(Photo(property_id=p.id, name=images.save_photo(p.id, buf.getvalue())))
            db.commit()
        yield c


@pytest.mark.parametrize("url", ["/", "/catalog", "/about", "/privacy", "/sitemap.xml", "/robots.txt"])
def test_pages_ok(client, url):
    assert client.get(url).status_code == 200


def test_home_shows_only_featured(client):
    with SessionLocal() as db:
        p = db.get(Property, 1)
        p.is_featured = False
        db.commit()
    assert "ул. Тестовая, 1" not in client.get("/").text
    with SessionLocal() as db:
        db.get(Property, 1).is_featured = True
        db.commit()
    assert "ул. Тестовая, 1" in client.get("/").text


def test_catalog_filters_and_htmx_partial(client):
    full = client.get("/catalog?rooms=2&price_max=6 000 000")
    assert "ул. Тестовая, 1" in full.text and "<html" in full.text
    assert "Продано" not in full.text  # проданные не в каталоге

    rent = client.get("/catalog?deal=rent")
    assert "Сдана" not in rent.text  # сданные не в каталоге

    partial = client.get("/catalog?rooms=3", headers={"HX-Request": "true"})
    assert "<html" not in partial.text and "Ничего не найдено" in partial.text


def test_property_url_is_numeric_id(client):
    r = client.get("/catalog/1-staryy-adres", follow_redirects=False)  # старые адреса со slug
    assert r.status_code == 301 and r.headers["location"] == "/catalog/1"
    page = client.get("/catalog/1")
    assert 'property="og:image"' in page.text and "_og.jpg" in page.text
    assert "RealEstateListing" in page.text


def test_contacts_merged_into_about(client):
    r = client.get("/contacts", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/about#contacts"
    about = client.get("/about").text
    assert 'id="contacts"' in about and 'name="phone"' in about  # контакты и форма на странице «Обо мне»


def test_unpublished_is_404(client):
    assert client.get("/catalog/4").status_code == 404
    assert client.get("/nope").status_code == 404


def test_photo_processed_to_webp(client):
    with SessionLocal() as db:
        ph = db.query(Photo).first()
    folder = images.property_dir(ph.property_id)
    thumb = Image.open(folder / f"{ph.name}_thumb.webp")
    assert thumb.format == "WEBP" and max(thumb.size) == images.WEBP_SIZES["thumb"]
    assert Image.open(folder / f"{ph.name}_og.jpg").size == images.OG_SIZE


def test_lead_validation_and_save(client):
    headers = {"HX-Request": "true"}
    bad = client.post("/lead", data={"name": "Иван", "phone": "123", "consent": "true"}, headers=headers)
    assert "Проверьте номер телефона" in bad.text

    no_consent = client.post("/lead", data={"name": "Иван", "phone": "89001234567"}, headers=headers)
    assert "согласие" in no_consent.text

    ok = client.post("/lead", data={"name": "Иван", "phone": "8 900 123-45-67", "consent": "true",
                                    "kind": "viewing", "property_id": "1"}, headers=headers)
    assert "заявка отправлена" in ok.text
    with SessionLocal() as db:
        lead = db.query(Lead).one()
    assert lead.phone == "+79001234567" and lead.property_id == 1


def test_honeypot_not_saved(client):
    with SessionLocal() as db:
        before = db.query(Lead).count()
    client.post("/lead", data={"name": "bot", "phone": "89001234567", "consent": "true", "website": "spam"})
    with SessionLocal() as db:
        assert db.query(Lead).count() == before


def test_admin_requires_login(client):
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code in (302, 303, 307)


def test_admin_login_with_cyrillic_password(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_password", "надёжный-пароль")
    bad = client.post("/admin/login", data={"username": settings.admin_username, "password": "не тот"})
    assert bad.status_code == 400 and "Осталось попыток" in bad.text
    ok = client.post("/admin/login", data={"username": settings.admin_username, "password": "надёжный-пароль"},
                     follow_redirects=False)
    assert ok.status_code == 302


def test_utils():
    assert status_for_deal("rent", "active") == "for_rent"
    assert status_for_deal("rent", "sold") == "rented"
    assert status_for_deal("sale", "rented") == "sold"
    assert status_for_deal("sale", "active") == "active"
    assert normalize_phone("+7 (900) 123-45-67") == "+79001234567"
    assert normalize_phone("9001234567") == "+79001234567"
    assert normalize_phone("12345") is None


def _login(client):
    from app.config import settings

    r = client.post("/admin/login", data={"username": settings.admin_username, "password": settings.admin_password},
                    follow_redirects=False)
    assert r.status_code == 302


def _jpeg(color="red", size=(900, 1200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def test_portfolio_settings_show_on_site(client):
    _login(client)
    assert client.get("/admin/portfolio").status_code == 200

    bad = client.post("/admin/portfolio", data={"about": "", "years_experience": "abc", "deals_closed": "5"})
    assert "Введите число" in bad.text and "Напишите пару предложений" in bad.text

    r = client.post(
        "/admin/portfolio",
        data={"about": "Первый абзац.\r\n\r\nВторой абзац.", "years_experience": "21", "deals_closed": "456"},
        files={"photo": ("me.jpg", _jpeg(), "image/jpeg")},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "saved=1" in r.headers["location"]

    about = client.get("/about").text
    assert '<p class="lead">Первый абзац.</p>' in about and "<p>Второй абзац.</p>" in about
    assert "<strong>456+</strong>" in about and "<strong>21</strong>" in about
    assert "/media/profile/realtor_" in about
    assert "<strong>456+</strong>" in client.get("/").text


def test_property_photos_reorder_and_delete(client):
    _login(client)
    with SessionLocal() as db:
        for color in ("green", "blue"):
            db.add(Photo(property_id=1, name=images.save_photo(1, _jpeg(color)), sort=9))
        db.commit()
        photos = db.query(Photo).filter_by(property_id=1).order_by(Photo.id).all()
    first, second, third = (ph.id for ph in photos)
    deleted_name = photos[1].name
    data = {"title": "2-комн. квартира", "deal_type": "sale", "property_type": "flat", "status": "active",
            "price": "5000000", "rooms": "2", "area_total": "50", "address": "ул. Тестовая, 1", "is_featured": "y",
            "is_published": "y", "save": "Сохранить",
            "photo_order": f"{third},{first},{second}", "photo_delete": str(second)}
    r = client.post("/admin/property/edit/1", data=data, files=[("photos_upload", ("", b"", "application/octet-stream"))],
                    follow_redirects=False)
    assert r.status_code == 302
    with SessionLocal() as db:
        left = [ph.id for ph in db.query(Photo).filter_by(property_id=1).order_by(Photo.sort)]
    assert left == [third, first]
    assert not list(images.property_dir(1).glob(f"{deleted_name}_*"))  # файлы удалённого фото стёрты


def test_lead_email_sent(client, monkeypatch):
    from app import mailer
    from app.config import settings

    sent = []
    monkeypatch.setattr(settings, "smtp_user", "site@example.com")
    monkeypatch.setattr(settings, "smtp_password", "app-password")
    monkeypatch.setattr(mailer, "_smtp_send", sent.append)
    r = client.post("/lead", data={"name": "Мария\r\nBcc: x@evil.com", "phone": "+7 912 000-11-22", "consent": "true",
                                   "kind": "viewing", "property_id": "1", "message": "Когда можно посмотреть?"},
                    headers={"HX-Request": "true"})
    assert "заявка отправлена" in r.text
    assert len(sent) == 1
    msg = sent[0]
    assert msg["To"] == settings.email and "Запись на просмотр" in msg["Subject"]
    assert "\n" not in msg["Subject"] and msg["Bcc"] is None  # перевод строки в имени не создаёт заголовков
    body = msg.get_body(("plain",)).get_content()
    assert "+79120000011" not in body and "+79120001122" in body and "/catalog/1" in body


def test_lead_email_skipped_when_not_configured(monkeypatch):
    from app import mailer

    called = []
    monkeypatch.setattr(mailer, "_smtp_send", called.append)
    mailer.send_lead(Lead(kind="callback", name="X", phone="+79000000000"), None)
    assert called == []


def test_login_lockout_after_five_failures(client):
    from app import login_guard
    from app.config import settings

    try:
        for left in (4, 3, 2, 1):
            r = client.post("/admin/login", data={"username": "admin", "password": "wrong"})
            assert r.status_code == 400 and f"Осталось попыток: {left}" in r.text
        r = client.post("/admin/login", data={"username": "admin", "password": "wrong"})
        assert r.status_code == 429 and "заблокирован до" in r.text
        # даже верный пароль не пускает, пока идёт блокировка
        r = client.post("/admin/login", data={"username": settings.admin_username, "password": settings.admin_password},
                        follow_redirects=False)
        assert r.status_code == 429
    finally:
        login_guard.reset()
    _login(client)  # после снятия блокировки вход снова работает


def test_admin_password_change(client):
    from app import admin_password, login_guard
    from app.config import settings

    _login(client)
    try:
        bad = client.post("/admin/password", data={"current": "wrong", "new": "новый-пароль-1", "repeat": "новый-пароль-1"})
        assert "Текущий пароль указан неверно" in bad.text
        mismatch = client.post("/admin/password", data={"current": settings.admin_password, "new": "новый-пароль-1", "repeat": "другой-пароль"})
        assert "не совпадают" in mismatch.text
        r = client.post("/admin/password", data={"current": settings.admin_password, "new": "новый-пароль-1", "repeat": "новый-пароль-1"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert client.get("/admin/property/list", follow_redirects=False).status_code == 200  # текущая сессия жива

        other = TestClient(app)
        assert other.post("/admin/login", data={"username": settings.admin_username, "password": settings.admin_password}).status_code == 400
        assert other.post("/admin/login", data={"username": settings.admin_username, "password": "новый-пароль-1"},
                          follow_redirects=False).status_code == 302
    finally:
        admin_password.reset()
        login_guard.reset()
    _login(client)

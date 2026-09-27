import asyncio
import logging
import secrets

import anyio
from markupsafe import Markup, escape
from PIL import UnidentifiedImageError
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.i18n import I18nConfig
from sqlalchemy import func, select
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import RedirectResponse
from wtforms import MultipleFileField, SelectField
from wtforms.widgets import HiddenInput

from app import admin_password, images, login_guard, profile as profile_store
from app.config import BASE_DIR, settings
from app.db import SessionLocal, engine
from app.models import (
    DEAL_TYPES,
    LEAD_KINDS,
    PROPERTY_TYPES,
    STATUSES,
    Lead,
    Photo,
    Profile,
    Property,
    Review,
    status_for_deal,
)
from app.templating import templates as site_templates
from app.utils import fmt_price

log = logging.getLogger(__name__)


def _same(given: object, expected: str) -> bool:
    # сравниваем байты: compare_digest не принимает строки с кириллицей
    return secrets.compare_digest(str(given or "").encode(), expected.encode())


class AdminAuth(AuthenticationBackend):
    templates = None  # шаблоны админки, выставляются в setup_admin

    async def _login_page(self, request: Request, error: str, status: int, locked: bool = False):
        return await self.templates.TemplateResponse(
            request, "sqladmin/login.html", {"error": error, "locked": locked}, status_code=status
        )

    async def login(self, request: Request):
        ip = request.client.host if request.client else "unknown"  # за nginx — реальный IP (--proxy-headers)
        until = login_guard.blocked_until(ip)
        if until:
            return await self._login_page(
                request, f"Слишком много неудачных попыток. Вход заблокирован до {until:%d.%m.%Y %H:%M}.", 429, locked=True
            )

        form = await request.form()
        password_ok = await anyio.to_thread.run_sync(admin_password.check, str(form.get("password") or ""))
        ok = _same(form.get("username"), settings.admin_username) & password_ok
        if not ok:
            await asyncio.sleep(1)  # замедляем перебор пароля
            left, until = login_guard.register_failure(ip)
            if until:
                return await self._login_page(
                    request,
                    f"Неверный логин или пароль. Попытки закончились — вход заблокирован до {until:%d.%m.%Y %H:%M}.",
                    429,
                    locked=True,
                )
            return await self._login_page(request, f"Неверный логин или пароль. Осталось попыток: {left}.", 400)

        login_guard.reset(ip)
        request.session["admin"] = True
        request.session["pv"] = admin_password.version()
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        # после смены пароля сессии со старой меткой перестают действовать
        return bool(request.session.get("admin")) and request.session.get("pv") == admin_password.version()


def _choices(d: dict[str, str]) -> list[tuple[str, str]]:
    return list(d.items())


class PropertyAdmin(ModelView, model=Property):
    name = "Объект"
    name_plural = "Объекты"
    add_label = "Добавить объект"
    edit_label = "Редактировать объект"
    icon = "fa-solid fa-house"
    page_size = 50

    column_list = [
        Property.id,
        Property.title,
        Property.deal_type,
        Property.price,
        Property.status,
        Property.is_featured,
        Property.is_published,
        Property.created_at,
    ]
    column_searchable_list = [Property.title, Property.address, Property.district]
    column_sortable_list = [Property.id, Property.price, Property.created_at]
    column_default_sort = [(Property.id, True)]
    column_formatters = {
        # превью и название в одном блоке с минимальной шириной — текст не наезжает на соседние колонки
        Property.title: lambda m, a: Markup(
            '<span style="display:inline-flex;align-items:center;gap:10px;min-width:220px;white-space:normal">'
            '{}<span>{}</span></span>'.format(
                '<img src="{}" style="height:40px;width:60px;flex:none;object-fit:cover;border-radius:4px">'.format(
                    m.cover.thumb
                )
                if m.cover
                else "",
                escape(m.title),
            )
        ),
        Property.created_at: lambda m, a: f"{m.created_at:%d.%m.%Y %H:%M}" if m.created_at else "",
        Property.deal_type: lambda m, a: DEAL_TYPES.get(m.deal_type, m.deal_type),
        Property.status: lambda m, a: STATUSES.get(m.status, m.status),
        Property.price: lambda m, a: fmt_price(m.price),
    }
    column_formatters_detail = {
        Property.deal_type: lambda m, a: DEAL_TYPES.get(m.deal_type, m.deal_type),
        Property.property_type: lambda m, a: PROPERTY_TYPES.get(m.property_type, m.property_type),
        Property.status: lambda m, a: STATUSES.get(m.status, m.status),
        Property.created_at: lambda m, a: f"{m.created_at:%d.%m.%Y %H:%M}" if m.created_at else "",
        Property.updated_at: lambda m, a: f"{m.updated_at:%d.%m.%Y %H:%M}" if m.updated_at else "",
    }
    column_details_exclude_list = [Property.photos]  # фото видны в форме редактирования
    column_labels = {
        Property.title: "Заголовок",
        Property.deal_type: "Сделка",
        Property.property_type: "Тип",
        Property.status: "Статус",
        Property.price: "Цена, ₽",
        Property.old_price: "Старая цена, ₽ (если снизили)",
        Property.rooms: "Комнат (0 — студия)",
        Property.area_total: "Площадь общая, м²",
        Property.area_living: "Жилая, м²",
        Property.area_kitchen: "Кухня, м²",
        Property.floor: "Этаж",
        Property.floors_total: "Этажей в доме",
        Property.year_built: "Год постройки",
        Property.house_type: "Тип дома",
        Property.district: "Район",
        Property.address: "Адрес",
        Property.lat: "Широта",
        Property.lon: "Долгота",
        Property.description: "Описание",
        Property.tags: "Теги через запятую",
        Property.is_featured: "На главную",
        Property.is_published: "Опубликован",
        Property.created_at: "Добавлен",
        Property.updated_at: "Изменён",
        Property.photos: "Фото",
    }
    form_excluded_columns = [Property.photos, Property.created_at, Property.updated_at]
    form_overrides = {"deal_type": SelectField, "property_type": SelectField, "status": SelectField}
    form_args = {
        "deal_type": {"choices": _choices(DEAL_TYPES), "label": "Сделка"},
        "property_type": {"choices": _choices(PROPERTY_TYPES), "label": "Тип"},
        "status": {
            "choices": _choices(STATUSES),
            "label": "Статус",
            "description": "Для аренды: «Сдается» / «Сдан». Если выбрать не тот — поправится автоматически.",
        },
        # координаты ставятся меткой на Яндекс.Карте (static/js/admin.js), сами поля скрыты
        "description": {"show_chars_count": False},
        "lat": {"widget": HiddenInput()},
        "lon": {"widget": HiddenInput()},
    }
    form_widget_args = {"description": {"rows": 10}}

    async def scaffold_form(self, rules=None):
        form_class = await super().scaffold_form(rules)
        form_class.photos_upload = MultipleFileField(
            "Фото",
            render_kw={"accept": "image/*,.heic,.heif", "multiple": True},
        )
        return form_class

    @staticmethod
    def _pop_uploads(data: dict) -> list:
        return [f for f in data.pop("photos_upload", None) or [] if getattr(f, "filename", "")]

    async def insert_model(self, request: Request, data: dict):
        uploads = self._pop_uploads(data)
        obj = await super().insert_model(request, data)
        await self._save_uploads(obj.id, uploads)
        return obj

    async def update_model(self, request: Request, pk: str, data: dict):
        uploads = self._pop_uploads(data)
        obj = await super().update_model(request, pk, data)
        form = await request.form()  # Starlette кэширует разобранную форму, повторного чтения нет
        self._apply_photo_changes(obj.id, str(form.get("photo_order", "")), str(form.get("photo_delete", "")))
        await self._save_uploads(obj.id, uploads)
        return obj

    @staticmethod
    def _apply_photo_changes(property_id: int, order: str, delete: str) -> None:
        """Порядок и удаление уже загруженных фото — из скрытых полей, которые заполняет admin.js."""
        to_delete = {int(x) for x in delete.split(",") if x.isdigit()}
        ordered = [int(x) for x in order.split(",") if x.isdigit()]
        if not (to_delete or ordered):
            return
        with SessionLocal() as db:
            photos = {ph.id: ph for ph in db.scalars(select(Photo).where(Photo.property_id == property_id))}
            for ph_id in to_delete & photos.keys():
                images.delete_photo_files(property_id, photos[ph_id].name)
                db.delete(photos.pop(ph_id))
            for i, ph_id in enumerate(x for x in ordered if x in photos):
                photos[ph_id].sort = i
            db.commit()

    async def on_model_change(self, data: dict, model: Property, is_created: bool, request: Request):
        # вызывается до записи data в модель
        data["status"] = status_for_deal(data.get("deal_type") or model.deal_type, data.get("status") or "active")

    async def _save_uploads(self, property_id: int, uploads: list) -> None:
        if not uploads:
            return
        with SessionLocal() as db:
            next_sort = (
                db.scalar(select(func.max(Photo.sort)).where(Photo.property_id == property_id)) or 0
            ) + 1
            for i, upload in enumerate(uploads):
                raw = await upload.read()
                try:
                    name = await anyio.to_thread.run_sync(images.save_photo, property_id, raw)
                except (UnidentifiedImageError, OSError):
                    log.warning("Пропущен файл, не являющийся изображением: %s", upload.filename)
                    continue
                db.add(Photo(property_id=property_id, name=name, sort=next_sort + i))
            db.commit()

    async def after_model_delete(self, model: Property, request: Request) -> None:
        images.delete_property_files(model.id)


class LeadAdmin(ModelView, model=Lead):
    name = "Заявка"
    name_plural = "Заявки"
    edit_label = "Заявка"
    icon = "fa-solid fa-phone"
    can_create = False

    column_list = [Lead.created_at, Lead.kind, Lead.name, Lead.phone, Lead.listing, Lead.is_processed]
    column_default_sort = [(Lead.created_at, True)]
    column_labels = {
        Lead.created_at: "Дата",
        Lead.kind: "Тип",
        Lead.name: "Имя",
        Lead.phone: "Телефон",
        Lead.message: "Сообщение",
        Lead.listing: "Объект",
        Lead.is_processed: "Обработана",
    }
    column_formatters = {Lead.kind: lambda m, a: LEAD_KINDS.get(m.kind, m.kind), Lead.created_at: lambda m, a: f"{m.created_at:%d.%m.%Y %H:%M}" if m.created_at else ""}
    column_formatters_detail = column_formatters
    form_columns = [Lead.is_processed, Lead.message]
    form_args = {"message": {"show_chars_count": False}}


class ReviewAdmin(ModelView, model=Review):
    name = "Отзыв"
    name_plural = "Отзывы"
    add_label = "Добавить отзыв"
    edit_label = "Редактировать отзыв"
    icon = "fa-solid fa-comment"

    column_list = [Review.author, Review.deal, Review.is_published, Review.created_at]
    column_labels = {
        Review.author: "Автор",
        Review.text: "Текст",
        Review.deal: "Подпись",
        Review.is_published: "Опубликован",
        Review.created_at: "Дата",
    }
    form_excluded_columns = [Review.created_at]
    form_args = {
        "text": {"show_chars_count": False},
        "deal": {"description": "Необязательно. Например: «Продажа 2-комн. квартиры» или «Покупка в ипотеку»."},
    }
    column_formatters = {Review.created_at: lambda m, a: f"{m.created_at:%d.%m.%Y %H:%M}" if m.created_at else ""}
    column_formatters_detail = column_formatters


def _int_in(value: object, lo: int, hi: int) -> int | None:
    try:
        n = int(str(value).strip())
    except ValueError:
        return None
    return n if lo <= n <= hi else None


class PortfolioAdmin(BaseView):
    name = "Настройка Портфолио"
    icon = "fa-solid fa-user-tie"

    @expose("/portfolio", methods=["GET", "POST"])
    async def portfolio(self, request: Request):
        with SessionLocal() as db:
            prof = db.get(Profile, 1)
            if prof is None:
                prof = Profile(id=1)
                db.add(prof)
                db.commit()
            errors: dict[str, str] = {}
            values = {"about": prof.about, "years_experience": prof.years_experience, "deals_closed": prof.deals_closed}

            if request.method == "POST":
                form = await request.form()
                values = {k: str(form.get(k, "")).strip() for k in values}
                years = _int_in(values["years_experience"], 0, 70)
                deals = _int_in(values["deals_closed"], 0, 100_000)
                if years is None:
                    errors["years_experience"] = "Введите число от 0 до 70"
                if deals is None:
                    errors["deals_closed"] = "Введите число от 0 до 100 000"
                if not values["about"]:
                    errors["about"] = "Напишите пару предложений о себе"

                new_photo = None
                upload = form.get("photo")
                if isinstance(upload, UploadFile) and upload.filename:
                    try:
                        new_photo = await anyio.to_thread.run_sync(images.save_profile_photo, await upload.read())
                    except (UnidentifiedImageError, OSError):
                        errors["photo"] = "Не удалось открыть файл — загрузите JPG, PNG или WebP"

                if errors:
                    images.delete_profile_photo(new_photo)
                else:
                    prof.about = values["about"].replace("\r\n", "\n")
                    prof.years_experience = years
                    prof.deals_closed = deals
                    if new_photo or form.get("photo_remove"):
                        images.delete_profile_photo(prof.photo)
                        prof.photo = new_photo
                    db.commit()
                    profile_store.reset_cache()
                    # PRG: после сохранения — GET, чтобы F5 не отправлял форму повторно
                    return RedirectResponse(request.url.path + "?saved=1", status_code=303)

            return await self.templates.TemplateResponse(
                request,
                "admin/portfolio.html",
                {
                    "prof": prof,
                    "values": values,
                    "errors": errors,
                    "saved": request.query_params.get("saved") == "1",
                },
            )


class PasswordAdmin(BaseView):
    name = "Смена пароля"
    icon = "fa-solid fa-key"

    @expose("/password", methods=["GET", "POST"])
    async def password(self, request: Request):
        error = None
        if request.method == "POST":
            form = await request.form()
            current, new, repeat = (str(form.get(k, "")) for k in ("current", "new", "repeat"))
            error = await anyio.to_thread.run_sync(admin_password.validate_new, current, new, repeat)
            if not error:
                await anyio.to_thread.run_sync(admin_password.set_password, new)
                request.session["pv"] = admin_password.version()  # текущая сессия остаётся, остальные — нет
                return RedirectResponse(request.url.path + "?saved=1", status_code=303)
        return await self.templates.TemplateResponse(
            request,
            "admin/password.html",
            {"error": error, "saved": request.query_params.get("saved") == "1", "min_length": admin_password.MIN_LENGTH},
        )


def setup_admin(app) -> Admin:
    auth = AdminAuth(secret_key=settings.secret_key, https_only=not settings.debug)
    admin = Admin(
        app,
        engine,
        title="Панель управления сайтом",
        templates_dir=str(BASE_DIR / "app" / "templates"),  # переопределения в templates/sqladmin/
        authentication_backend=auth,
        i18n_config=I18nConfig(default_locale="ru"),
    )
    auth.templates = admin.templates
    admin.templates.env.globals["settings"] = settings
    admin.templates.env.globals["static_v"] = site_templates.env.globals["static_v"]
    for view in (PropertyAdmin, LeadAdmin, ReviewAdmin):
        admin.add_view(view)
    admin.add_base_view(PortfolioAdmin)
    admin.add_base_view(PasswordAdmin)
    return admin

"""Отправка заявок на почту через SMTP.

Проверка настроек на сервере: .venv/bin/python -m app.mailer — пришлёт тестовое письмо.
"""

import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from app.config import settings
from app.models import LEAD_KINDS, Lead, Property

log = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.smtp_user and settings.smtp_password and settings.leads_email_to)


def _one_line(text: str) -> str:
    # переносы строк в заголовке письма недопустимы (и опасны — подмена заголовков)
    return " ".join(text.split())


def build_lead_email(lead: Lead, prop: Property | None) -> EmailMessage:
    kind = LEAD_KINDS.get(lead.kind, "Заявка")
    rows = [("Имя", lead.name), ("Телефон", lead.phone)]
    prop_url = f"{settings.base_url}{prop.url}" if prop else ""
    if prop:
        rows.append(("Объект", f"{prop.short_title}, {prop.address} — {prop_url}"))
    if lead.message:
        rows.append(("Сообщение", lead.message))
    rows.append(("Время", datetime.now().strftime("%d.%m.%Y %H:%M")))

    msg = EmailMessage()
    msg["Subject"] = _one_line(f"Заявка с сайта: {kind} — {lead.name}")
    msg["From"] = formataddr((f"Сайт {settings.realtor_name}", settings.smtp_user))
    msg["To"] = settings.leads_email_to
    msg.set_content(f"{kind}\n\n" + "\n".join(f"{k}: {v}" for k, v in rows))

    html_rows = []
    for key, value in rows:
        if key == "Телефон":
            cell = f'<a href="tel:{escape(value)}">{escape(value)}</a>'
        elif key == "Объект":
            cell = f'<a href="{escape(prop_url)}">{escape(prop.short_title)}</a>, {escape(prop.address)}'
        else:
            cell = escape(value).replace("\n", "<br>")
        html_rows.append(
            f'<tr><td style="padding:6px 16px 6px 0;color:#6a706b;vertical-align:top">{key}</td>'
            f'<td style="padding:6px 0">{cell}</td></tr>'
        )
    msg.add_alternative(
        f'<div style="font-family:Arial,sans-serif;font-size:15px;color:#1d2320">'
        f'<h2 style="margin:0 0 12px;color:#1f4a3f">{escape(kind)}</h2>'
        f'<table style="border-collapse:collapse">{"".join(html_rows)}</table>'
        f'<p style="color:#6a706b;font-size:13px">Все заявки — в админке: {settings.base_url}/admin</p></div>',
        subtype="html",
    )
    return msg


def _smtp_send(msg: EmailMessage) -> None:
    ctx = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx, timeout=15) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:  # 587 и прочие — через STARTTLS
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ctx)
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


def send_lead(lead: Lead, prop: Property | None) -> None:
    """Вызывается фоном после ответа посетителю, поэтому медленный SMTP не тормозит сайт."""
    if not is_configured():
        log.info("Почта не настроена (SMTP_USER/SMTP_PASSWORD), письмо о заявке не отправлено")
        return
    try:
        _smtp_send(build_lead_email(lead, prop))
    except (smtplib.SMTPException, OSError):
        # Заявка уже сохранена в БД — риелтор увидит её в админке даже при сбое почты
        log.exception("Не удалось отправить заявку на почту")


if __name__ == "__main__":
    if not is_configured():
        raise SystemExit("Заполните SMTP_USER и SMTP_PASSWORD в .env")
    test = Lead(kind="question", name="Тест", phone="+79000000000", message="Проверка отправки заявок на почту")
    _smtp_send(build_lead_email(test, None))
    print(f"Отправлено на {settings.leads_email_to}")

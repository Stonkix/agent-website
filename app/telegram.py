import logging
from html import escape

import httpx

from app.config import settings
from app.models import LEAD_KINDS, Lead, Property

log = logging.getLogger(__name__)


def format_lead(lead: Lead, prop: Property | None) -> str:
    lines = [
        f"🔔 <b>{escape(LEAD_KINDS.get(lead.kind, 'Заявка'))}</b>",
        f"👤 {escape(lead.name)}",
        f"📞 {escape(lead.phone)}",
    ]
    if prop:
        lines.append(
            f'🏠 <a href="{settings.base_url}{prop.url}">{escape(prop.short_title)}</a>, '
            f"{escape(prop.address)}"
        )
    if lead.message:
        lines.append(f"💬 {escape(lead.message)}")
    return "\n".join(lines)


async def send_message(text: str) -> None:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        log.warning("Telegram не настроен, сообщение не отправлено:\n%s", text)
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except httpx.HTTPError:
        # Заявка уже сохранена в БД — риелтор увидит её в админке даже при сбое Telegram
        log.exception("Не удалось отправить заявку в Telegram")

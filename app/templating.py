import json
import time
from datetime import datetime

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.config import BASE_DIR, settings
from app.models import DEAL_TYPES, LEAD_KINDS, PROPERTY_TYPES, STATUSES
from app.profile import get_profile
from app.utils import fmt_num, fmt_price

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


def _json_ld(data: dict) -> Markup:
    # "</" экранируем, чтобы текст описания не мог закрыть <script>
    return Markup(json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def _plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


templates.env.globals.update(
    settings=settings,
    DEAL_TYPES=DEAL_TYPES,
    PROPERTY_TYPES=PROPERTY_TYPES,
    STATUSES=STATUSES,
    LEAD_KINDS=LEAD_KINDS,
    static_v=int(time.time()),  # сброс кэша статики при каждом рестарте
    now=datetime.now,
    profile=get_profile,  # портфолио из админки: фото, о себе, цифры
)
templates.env.filters.update(
    price=fmt_price,
    money=lambda v: f"{int(v):,}".replace(",", " ") if v else "",
    num=fmt_num,
    json_ld=_json_ld,
    plural=_plural,
)

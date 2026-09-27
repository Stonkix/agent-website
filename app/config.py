from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    debug: bool = False
    base_url: str = "http://127.0.0.1:8000"  # без слеша в конце, нужен для sitemap/OG
    secret_key: str = "change-me"
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'site.db').as_posix()}"
    media_dir: Path = BASE_DIR / "media"

    admin_username: str = "admin"
    admin_password: str = "admin"

    # Заявки на почту. Для mail.ru нужен «пароль для внешних приложений», не обычный пароль от ящика
    smtp_host: str = "smtp.mail.ru"
    smtp_port: int = 465
    smtp_user: str = ""  # ящик-отправитель, например 89036964555@mail.ru
    smtp_password: str = ""
    leads_email: str = ""  # куда слать заявки; пусто — на EMAIL из контактов

    # Данные риелтора — выводятся в шапке, подвале, контактах и PDF/OG
    site_name: str = "Наталья Кошелева — недвижимость"
    realtor_name: str = "Наталья Кошелева"
    realtor_title: str = "Частный риелтор"
    city: str = "Калуга"
    phone: str = "+7 903 696-45-55"
    email: str = "89036964555@mail.ru"
    telegram: str = "movementhome"  # без @
    max_url: str = "https://web.max.ru/356030245"  # пусто — кнопки Max не показываются
    office_address: str = ""
    legal_info: str = "Самозанятая Кошелева Н. В., ИНН 400301000301"
    yandex_metrika_id: str = ""
    # Ключ JavaScript API и Геокодера: developer.tech.yandex.ru → «Подключить API»
    yandex_maps_api_key: str = ""
    map_center_lat: float = 54.513845  # центр карты в админке, пока метка не поставлена
    map_center_lon: float = 36.261215

    @property
    def leads_email_to(self) -> str:
        return self.leads_email or self.email

    @property
    def phone_href(self) -> str:
        return "tel:+" + "".join(c for c in self.phone if c.isdigit())


settings = Settings()

# Сайт риелтора

FastAPI + SQLite + Jinja2 + HTMX + sqladmin. Без Node, без сборки фронтенда, без внешних CDN (htmx и Leaflet лежат в `app/static/vendor`).

## Что есть

| Страница | Адрес |
|---|---|
| Главная: УТП, быстрый поиск, актуальные объекты, преимущества, этапы, форма оценки, отзывы | `/` |
| Каталог с фильтрами без перезагрузки (HTMX), сортировка, пагинация | `/catalog` |
| Карточка объекта: галерея + лайтбокс, характеристики, карта OSM, похожие объекты, «Скачать PDF» (печать) | `/catalog/{id}` |
| Обо мне, услуги, недавние сделки (проданные и сданные объекты), отзывы, контакты с формой (старый `/contacts` ведёт сюда) | `/about` |
| Политика ПДн и текст согласия (шаблон — проверьте с юристом) | `/privacy` |
| `sitemap.xml`, `robots.txt`, 404 | |
| Админка: объекты, фото, заявки, отзывы | `/admin` |

Под капотом:
- **Фото**: загружаются пачкой в форме объекта → поворот по EXIF, удаление метаданных (в т.ч. GPS с телефона), WebP 800px и 1920px + JPEG 1200×630 для превью в мессенджерах. Порядок и удаление — в разделе «Фото».
- **Заявки** сохраняются в БД и уходят на почту (SMTP) и/или в Telegram — что настроено в `.env`. Защита от спама: honeypot-поле, лимит по IP, лимиты в nginx.
- **SEO**: короткие адреса `/catalog/12`, Open Graph, `RealEstateListing` и `RealEstateAgent` (Schema.org), sitemap с `lastmod`.
- **Статусы**: «В продаже» / «Продано» для продажи, «Сдается» / «Сдан» для аренды. Проданные и сданные уходят из каталога в «Недавние сделки». Бейджи «Новинка» (14 дней) и «Снижена цена».
- **Админка**: метка объекта ставится кликом на Яндекс.Карте, фото перетаскиваются мышкой пачкой.

## Запуск локально (Windows)

```bash
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
echo DEBUG=true> .env
.venv\Scripts\python seed.py
.venv\Scripts\uvicorn app.main:app --reload
```

Сайт: http://127.0.0.1:8000, админка: http://127.0.0.1:8000/admin (в режиме `DEBUG` логин/пароль `admin`/`admin`).
`seed.py` заливает 10 демо-объектов с условными фото; повторный запуск пересоздаёт их.

Тесты: `.venv\Scripts\python -m pytest -q`

## Что заполнить перед запуском

1. `.env` по образцу `.env.example`: контакты, реквизиты, `BASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`. Без них при `DEBUG=false` приложение не стартует.
2. Фото, текст «О себе», стаж и число сделок — в админке, раздел «Настройка Портфолио».
3. Превью ссылки на сайт: `python scripts/make_og_image.py` перегенерирует `og-default.jpg` с вашим именем.
4. Тексты в `app/templates/index.html` и `about.html` — это заготовки: преимущества, цены, биография.
5. Яндекс.Карты: ключ «JavaScript API и HTTP Геокодер» на developer.tech.yandex.ru → `YANDEX_MAPS_API_KEY`. Без ключа метку можно ставить кликом, но поиск по адресу не работает.
6. Почта для заявок: в mail.ru «Настройки → Безопасность → Пароли для внешних приложений» создайте пароль с доступом к SMTP и впишите его в `SMTP_PASSWORD`. Проверка: `.venv/bin/python -m app.mailer` пришлёт тестовое письмо.
7. Telegram (необязательно): создайте бота у @BotFather → `TELEGRAM_BOT_TOKEN`; напишите боту что-нибудь, узнайте свой id у @userinfobot → `TELEGRAM_CHAT_ID`. Можно добавить бота в рабочую группу и указать id группы.

## Деплой на VDS (Ubuntu 24.04)

```bash
# 1. Пакеты и пользователь
sudo apt update && sudo apt install -y python3-venv nginx certbot python3-certbot-nginx
sudo adduser --system --group --home /srv/rieltor rieltor

# 2. Код (git clone или scp) в /srv/rieltor, затем:
cd /srv/rieltor
sudo -u rieltor python3 -m venv .venv
sudo -u rieltor .venv/bin/pip install -r requirements.txt
sudo -u rieltor cp .env.example .env && sudo -u rieltor nano .env
sudo -u rieltor mkdir -p data media

# 3. Сервис
sudo cp deploy/rieltor.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now rieltor

# 4. nginx + HTTPS (поменяйте example.ru в конфиге)
sudo cp deploy/nginx.conf /etc/nginx/sites-available/rieltor
sudo ln -s /etc/nginx/sites-available/rieltor /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d example.ru -d www.example.ru

# 5. Файрвол и бэкапы
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
sudo chmod +x deploy/backup.sh && sudo crontab -e   # 30 3 * * * /srv/rieltor/deploy/backup.sh
```

SSH: вход по ключу, `PasswordAuthentication no` и `PermitRootLogin no` в `/etc/ssh/sshd_config`.

Обновление: `git pull && sudo systemctl restart rieltor`.

Для 152-ФЗ: VDS должен быть в РФ, а оператору ПДн нужно подать уведомление в Роскомнадзор.

## Структура

```
app/
  main.py        приложение, роуты, 404
  config.py      настройки из .env
  models.py      Property, Photo, Lead, Review
  admin.py       sqladmin: формы, загрузка фото, авторизация
  images.py      обработка фото (Pillow)
  telegram.py    отправка заявок
  routes/        pages (страницы и фильтры), leads (формы), seo (sitemap/robots)
  templates/     Jinja2; partials/ — куски для HTMX
  static/        css, js, img, vendor (htmx, leaflet)
deploy/          nginx, systemd, backup
seed.py          демо-данные
```

## Куда расти

- **Alembic** — как только понадобится поменять модели на живой базе (сейчас таблицы создаёт `create_all`, он не умеет добавлять колонки).
- **Настоящий PDF-буклет** через WeasyPrint, если печати из браузера станет мало.
- **Яндекс.Карты** вместо OSM (нужен API-ключ) и геокодер адреса в админке.
- **Подборки для клиента**: ссылка с выбранными объектами.

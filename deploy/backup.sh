#!/bin/sh
# Ежедневный бэкап БД и фото. cron (sudo crontab -e):
#   30 3 * * * /srv/rieltor/deploy/backup.sh
# Бэкап на том же сервере не спасёт от потери VDS — копируйте $DEST наружу (rclone в S3/Яндекс Object Storage).
set -eu

APP=/srv/rieltor
DEST=/var/backups/rieltor
KEEP_DAYS=14
STAMP=$(date +%F)

mkdir -p "$DEST"
# Онлайн-бэкап SQLite: корректен даже во время записи
"$APP/.venv/bin/python" -c "import sqlite3, sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))" \
    "$APP/data/site.db" "$DEST/site-$STAMP.db"
tar -czf "$DEST/media-$STAMP.tar.gz" -C "$APP" media
find "$DEST" -type f -mtime +$KEEP_DAYS -delete

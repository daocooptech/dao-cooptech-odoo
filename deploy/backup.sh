#!/usr/bin/env bash
# Суточный снимок боевой базы.
#
# Отдельно от выкатки: `update.sh` делает снимок перед обновлением
# модулей, но выкатки может не быть неделю, а данные на платформе
# копятся каждый день. Двести проектов, пятьсот сделок, тысяча вкладов
# держались на одной копии — на той, что в самой базе.
#
# Пункт 19 разбора архитектора.
#
#   bash backup.sh          — снимок сейчас
#   systemctl start coop-backup.service
set -euo pipefail

DB=koopeh
BACKUP_DIR=/var/backups/coop
KEEP=7            # снимков базы
KEEP_STORE=3      # копий файлового хранилища
# Путь берётся из конфига: `data_dir` на боевой — /var/lib/coop,
# и хранилище лежит в нём, а не рядом с кодом.
DATA_DIR=$(awk -F'= *' '/^data_dir/ {print $2}' /etc/coop-odoo.conf 2>/dev/null)
STORE=$DATA_DIR/filestore
# Ключи узла федерации (coop_federation) — вне базы и вне хранилища: в базе
# секрету не место. Потеряв файл, узел не сможет продолжить свой журнал —
# только сменить ключ резервным.
KEYS=$DATA_DIR/federation

# Имя снимка — по платформе, а не по базе (владелец, 28.09.2026: «пусть
# будет cooptech»). Прежние `koopeh-…` счёт сроков видит наравне с новыми.
SNAP=cooptech
OLD_SNAP=koopeh

mkdir -p "$BACKUP_DIR"
DUMP="$BACKUP_DIR/$SNAP-$(date +%F-%H%M%S).dump"

sudo -u postgres pg_dump -Fc "$DB" > "$DUMP"
if [ ! -s "$DUMP" ]; then
    rm -f "$DUMP"
    echo "Снимок не сделан: pg_dump вернул пустой файл" >&2
    exit 1
fi

# Файловое хранилище — вторая половина базы.
#
# В нём лежат снимки объявлений, знаки организаций, вложения переписки.
# Дамп без него восстановит записи, у которых картинки не открываются, —
# и выглядеть это будет как сломанная платформа, а не как неполная копия.
if [ -d "$STORE" ]; then
    tar -czf "${DUMP%.dump}-filestore.tar.gz" -C "$(dirname "$STORE")" \
        "$(basename "$STORE")"
fi
if [ -d "$KEYS" ]; then
    tar -czf "${DUMP%.dump}-federation-keys.tar.gz" -C "$DATA_DIR" federation
    chmod 600 "${DUMP%.dump}-federation-keys.tar.gz"
fi

# Сколько хранить. База и хранилище разного веса: дамп тринадцать
# мегабайт, хранилище почти двести, и семь его копий заняли бы
# полтора гигабайта из восьми свободных. Снимков базы держим семь,
# хранилища три: картинки меняются реже записей, и возвращать их на
# неделю назад приходится куда реже.
#
# Считаем по времени изменения, а не по имени: имя с датой удобно
# читать, но сортировать по нему значит зависеть от формата даты.
#
# `|| true` обязателен: когда прежних `koopeh-…` не останется, ls вернёт
# ошибку на пустом шаблоне, и при pipefail снимок оборвался бы здесь.
newest() { ls -1t "$BACKUP_DIR/$SNAP-"$1 "$BACKUP_DIR/$OLD_SNAP-"$1 2>/dev/null || true; }
newest '*.dump' | tail -n +$((KEEP + 1)) | xargs -r rm -f
newest '*-filestore.tar.gz' | tail -n +$((KEEP_STORE + 1)) | xargs -r rm -f
newest '*-federation-keys.tar.gz' | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "Снимок: $DUMP ($(du -h "$DUMP" | cut -f1))"

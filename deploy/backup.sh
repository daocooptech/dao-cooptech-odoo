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

mkdir -p "$BACKUP_DIR"
DUMP="$BACKUP_DIR/$DB-$(date +%F-%H%M%S).dump"

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
ls -1t "$BACKUP_DIR/$DB-"*.dump 2>/dev/null | tail -n +$((KEEP + 1)) \
    | xargs -r rm -f
ls -1t "$BACKUP_DIR/$DB-"*-filestore.tar.gz 2>/dev/null \
    | tail -n +$((KEEP_STORE + 1)) | xargs -r rm -f
ls -1t "$BACKUP_DIR/$DB-"*-federation-keys.tar.gz 2>/dev/null \
    | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "Снимок: $DUMP ($(du -h "$DUMP" | cut -f1))"

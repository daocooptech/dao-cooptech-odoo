#!/usr/bin/env bash
# Перенести базу и файловое хранилище со стенда разработки.
#
#   bash restore.sh /path/koopeh.dump [/path/filestore.tar.gz]
#
# Существующая база с тем же именем удаляется — на боевом сервере это
# делается осознанно и только пока платформа не открыта участникам.
set -euo pipefail

DUMP="$1"
STORE="${2:-}"
DB=koopeh
USER=odoo

systemctl stop coop-odoo || true

sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1 && {
    echo "Удаляю прежнюю базу $DB"
    sudo -u postgres psql -c "DROP DATABASE $DB;"
}
sudo -u postgres psql -c "CREATE DATABASE $DB OWNER $USER;"

# Дамп обычно лежит в домашнем каталоге root, а восстановление идёт от
# другого пользователя — до файла он не дотянется. Копия в общем
# каталоге снимает вопрос и убирается за собой.
WORK="/tmp/coop-restore.dump"
install -m 644 "$DUMP" "$WORK"
trap 'rm -f "$WORK"' EXIT

# Формат определяется по самому файлу, а не по расширению — и без
# внешних утилит: `file` на чистом Debian не установлен, а её отсутствие
# уводило разбор в двоичную ветку, где текстовый дамп «не похож на
# архив».
#
# Двоичный дамп читается только своей версией PostgreSQL или новее:
# перенос со стенда, где версия свежее серверной, падает на «unsupported
# version in file header». Текстовый переносится между версиями, поэтому
# он и предпочтителен — но принимаем оба.
if gzip -t "$WORK" 2>/dev/null; then
    echo "Восстанавливаю из сжатого текстового дампа"
    ( cd /tmp && gunzip -c "$WORK" | sudo -u "$USER" psql -q -d "$DB" )         > /tmp/coop-restore.out 2>&1
    echo "строк в журнале восстановления: $(wc -l < /tmp/coop-restore.out)"
    # `|| true` обязателен: grep -c при нуле совпадений возвращает
    # единицу, и при set -e чистое восстановление обрывало скрипт ровно
    # там, где всё прошло хорошо — до переноса файлового хранилища.
    echo "ошибок: $(grep -c 'ОШИБКА\|ERROR' /tmp/coop-restore.out || true)"
elif head -c 5 "$WORK" | grep -q "PGDMP"; then
    echo "Восстанавливаю из двоичного дампа"
    ( cd /tmp && sudo -u "$USER" pg_restore -d "$DB" --no-owner --role="$USER" "$WORK" )
else
    echo "Восстанавливаю из текстового дампа"
    ( cd /tmp && sudo -u "$USER" psql -q -d "$DB" -f "$WORK" )         > /tmp/coop-restore.out 2>&1
    echo "строк в журнале восстановления: $(wc -l < /tmp/coop-restore.out)"
fi

if [ -n "$STORE" ]; then
    echo "Разворачиваю файловое хранилище"
    mkdir -p /var/lib/coop/filestore
    rm -rf "/var/lib/coop/filestore/$DB"
    tar -xzf "$STORE" -C /var/lib/coop/filestore
    chown -R "$USER:$USER" /var/lib/coop/filestore
fi

# Почтовые серверы и запланированные задания переносить нельзя: боевой
# стенд не должен разослать письма от имени стенда разработки.
sudo -u postgres psql -d "$DB" <<'SQL'
UPDATE ir_mail_server SET active = false;
UPDATE ir_cron SET active = false WHERE cron_name ILIKE '%mail%';
SQL

systemctl start coop-odoo
echo "Готово. Проверка: journalctl -u coop-odoo -f"

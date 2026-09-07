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
sudo -u "$USER" pg_restore -d "$DB" --no-owner --role="$USER" "$DUMP"

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

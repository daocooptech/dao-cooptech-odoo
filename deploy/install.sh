#!/usr/bin/env bash
# Первичная установка ДАО КООПТЕХ на чистый сервер (Debian/Ubuntu).
#
# Ставит PostgreSQL, Python и Odoo 19 с двумя наборами дополнений —
# rudoo-addons (российская сборка) и coop-addons (наши разделы), — и
# поднимает платформу как службу systemd за nginx.
#
# Запускать один раз от root:
#
#   bash install.sh
#
# Повторный запуск безопасен: всё, что уже стоит, пропускается.
set -euo pipefail

ODOO_USER=odoo
ODOO_HOME=/opt/coop
DB_NAME=koopeh
DB_USER=odoo
DB_PASS="${COOP_DB_PASS:-odoo}"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# ── Пакеты ───────────────────────────────────────────────────────────────
say "Системные пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    git curl build-essential python3 python3-venv python3-dev \
    postgresql postgresql-client \
    libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libssl-dev \
    libjpeg-dev zlib1g-dev libpq-dev libffi-dev \
    node-less nginx fonts-dejavu-core

# wkhtmltopdf нужен только для печатных форм. Его нет в свежих репозиториях
# Debian, и без него платформа работает — поэтому ставим, если есть, и не
# валимся, если нет.
apt-get install -y -qq wkhtmltopdf || echo "wkhtmltopdf не поставлен — печать в PDF будет недоступна"

# ── Пользователь и каталоги ──────────────────────────────────────────────
say "Пользователь $ODOO_USER и каталоги"
# Исходники принадлежат пользователю платформы, а обслуживающие команды
# идут от root: без этой пометки git отказывается работать в чужом
# каталоге («dubious ownership»), и обновление молча не доезжает.
for d in "$ODOO_HOME/odoo" "$ODOO_HOME/rudoo-addons" "$ODOO_HOME/coop-addons"; do
    git config --global --get-all safe.directory | grep -qxF "$d"         || git config --global --add safe.directory "$d"
done
id -u "$ODOO_USER" >/dev/null 2>&1 || useradd -m -d "$ODOO_HOME" -s /bin/bash "$ODOO_USER"
mkdir -p "$ODOO_HOME" /var/log/coop /var/lib/coop
chown -R "$ODOO_USER:$ODOO_USER" "$ODOO_HOME" /var/log/coop /var/lib/coop

# ── База ─────────────────────────────────────────────────────────────────
say "PostgreSQL"
systemctl enable --now postgresql
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 \
    || sudo -u postgres psql -c "CREATE ROLE $DB_USER LOGIN CREATEDB PASSWORD '$DB_PASS';"

# ── Исходники ────────────────────────────────────────────────────────────
say "Odoo и дополнения"
clone_or_pull() {
    local url="$1" dir="$2" branch="$3" depth="${4:-}"
    if [ -d "$dir/.git" ]; then
        sudo -u "$ODOO_USER" git -C "$dir" fetch --quiet origin "$branch"
        sudo -u "$ODOO_USER" git -C "$dir" reset --hard --quiet "origin/$branch"
    else
        # shellcheck disable=SC2086
        sudo -u "$ODOO_USER" git clone --quiet $depth --branch "$branch" "$url" "$dir"
    fi
}

# Odoo клонируется мелко: полная история — полтора гигабайта, и на сервере
# она не нужна ни для чего.
clone_or_pull https://github.com/odoo/odoo.git        "$ODOO_HOME/odoo"         19.0 "--depth 1"
clone_or_pull https://git.ruodoo.ru/ruodoo-public/public.git "$ODOO_HOME/rudoo-addons" master "--depth 1"
clone_or_pull https://github.com/daocooptech/dao-cooptech-odoo.git "$ODOO_HOME/coop-addons" main

# ── Окружение Python ─────────────────────────────────────────────────────
say "Виртуальное окружение"
if [ ! -x "$ODOO_HOME/venv/bin/python" ]; then
    sudo -u "$ODOO_USER" python3 -m venv "$ODOO_HOME/venv"
fi
sudo -u "$ODOO_USER" "$ODOO_HOME/venv/bin/pip" install -q --upgrade pip wheel setuptools
sudo -u "$ODOO_USER" "$ODOO_HOME/venv/bin/pip" install -q psycopg2-binary
sudo -u "$ODOO_USER" "$ODOO_HOME/venv/bin/pip" install -q -r "$ODOO_HOME/odoo/requirements.txt"

# ── Конфигурация ─────────────────────────────────────────────────────────
say "Конфигурация"
install -o "$ODOO_USER" -g "$ODOO_USER" -m 640 \
    "$ODOO_HOME/coop-addons/deploy/odoo.conf" /etc/coop-odoo.conf
sed -i "s|^db_password = .*|db_password = $DB_PASS|" /etc/coop-odoo.conf

install -m 644 "$ODOO_HOME/coop-addons/deploy/coop-odoo.service" /etc/systemd/system/
install -m 644 "$ODOO_HOME/coop-addons/deploy/coop-update.service" /etc/systemd/system/
install -m 644 "$ODOO_HOME/coop-addons/deploy/coop-update.timer" /etc/systemd/system/
install -m 644 "$ODOO_HOME/coop-addons/deploy/nginx-coop.conf" /etc/nginx/sites-available/coop
ln -sf /etc/nginx/sites-available/coop /etc/nginx/sites-enabled/coop
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable coop-odoo.service coop-update.timer
nginx -t && systemctl reload nginx

say "Готово"
cat <<TEXT
Дальше — данные:
  · перенести базу:      bash $ODOO_HOME/coop-addons/deploy/restore.sh /path/koopeh.dump
  · или поставить с нуля: sudo -u $ODOO_USER $ODOO_HOME/venv/bin/python $ODOO_HOME/odoo/odoo-bin \\
                              -c /etc/coop-odoo.conf -d $DB_NAME -i coop_theme --stop-after-init

Запуск:   systemctl start coop-odoo
Проверка: systemctl status coop-odoo; journalctl -u coop-odoo -f
Обновление раз в сутки включено таймером coop-update.timer.
TEXT

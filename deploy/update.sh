#!/usr/bin/env bash
# Свежая версия платформы: подтянуть код, обновить изменившиеся модули,
# перезапустить службу.
#
# Запускается таймером раз в сутки и вручную:  bash update.sh
#
# Обновляются только те модули, файлы которых изменились: обновление всех
# подряд на каждой ночи занимает минуты и трогает данные без нужды.
set -euo pipefail

ODOO_HOME=/opt/coop
CONF=/etc/coop-odoo.conf
DB=koopeh
USER=odoo

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run() { sudo -u "$USER" "$@"; }

cd "$ODOO_HOME/coop-addons"
before=$(run git rev-parse HEAD)
run git fetch --quiet origin main
run git reset --hard --quiet origin/main
after=$(run git rev-parse HEAD)

if [ "$before" = "$after" ]; then
    say "Изменений нет ($after)"
    exit 0
fi

say "Обновление $before → $after"

# Какие модули задеты. Первый уровень каталогов и есть имена модулей.
changed=$(run git diff --name-only "$before" "$after" \
          | awk -F/ 'NF>1 {print $1}' | sort -u \
          | while read -r d; do [ -f "$ODOO_HOME/coop-addons/$d/__manifest__.py" ] && echo "$d"; done \
          | paste -sd, -)

if [ -z "$changed" ]; then
    say "Изменения вне модулей — только перезапуск"
else
    say "Обновляю: $changed"
    systemctl stop coop-odoo
    run "$ODOO_HOME/venv/bin/python" "$ODOO_HOME/odoo/odoo-bin" \
        -c "$CONF" -d "$DB" -u "$changed" --stop-after-init --no-http
fi

# Собранные стили и скрипты сбрасываются всегда: адрес сборки Odoo держит
# в памяти процесса, и без перезапуска участник получает старый файл по
# новому коду. Отсюда же и порядок: сначала сброс, потом старт.
run "$ODOO_HOME/venv/bin/python" "$ODOO_HOME/odoo/odoo-bin" shell \
    -c "$CONF" -d "$DB" --no-http <<'PYEOF'
env['ir.attachment'].search([('url', 'like', '/web/assets/%')]).unlink()
env.cr.commit()
PYEOF

systemctl restart coop-odoo
say "Готово: $(run git log -1 --format='%h %s')"

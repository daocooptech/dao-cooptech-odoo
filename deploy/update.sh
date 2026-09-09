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

# Сценарии запуска лежат в этом же репозитории, но systemd читает их
# из /etc. Раньше их переносил только install.sh, и правка таймера
# доезжала до сервера, ничего не меняя. Теперь блоки сверяются при каждом
# обновлении: изменились — переносим и перечитываем.
for unit in coop-odoo.service coop-update.service coop-update.timer; do
    src="$ODOO_HOME/coop-addons/deploy/$unit"
    dst="/etc/systemd/system/$unit"
    if [ -f "$src" ] && ! cmp -s "$src" "$dst"; then
        say "Обновляю $unit"
        cp "$src" "$dst"
        units_changed=1
    fi
done
if [ "${units_changed:-0}" = "1" ]; then
    systemctl daemon-reload
    systemctl restart coop-update.timer || true
fi

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

# Прогрев: собрать пакеты стилей и скриптов сразу, а не при первом
# заходе участника.
#
# Сборка стоит около десяти секунд на этой машине, и без прогрева их
# платит тот, кто зашёл первым после ночного обновления. Ждать десять
# секунд на пустой белой странице — ровно то, из-за чего платформу
# считают неработающей.
say "Прогреваю пакеты"
for attempt in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60         http://127.0.0.1:8069/web/login || true)
    [ "$code" = "200" ] && break
    sleep 2
done
bash "$ODOO_HOME/coop-addons/deploy/warmup.sh" || true
say "Готово: $(run git log -1 --format='%h %s')"

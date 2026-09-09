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

# Блоки systemd сверяются до проверки «изменений нет»: сами блоки могли
# приехать прошлым обновлением, а поставить их было некому — сценарий
# выходил раньше. Ровно на этом минутный таймер и не встал с первого раза.
#
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
# Конфиг nginx и страница «обновляемся» тоже лежат в репозитории.
mkdir -p /var/www/coop
if ! cmp -s "$ODOO_HOME/coop-addons/deploy/maintenance.html" /var/www/coop/maintenance.html; then
    cp "$ODOO_HOME/coop-addons/deploy/maintenance.html" /var/www/coop/maintenance.html
    say "Обновляю страницу обновления"
fi
if ! cmp -s "$ODOO_HOME/coop-addons/deploy/nginx-coop.conf" /etc/nginx/sites-available/coop; then
    cp "$ODOO_HOME/coop-addons/deploy/nginx-coop.conf" /etc/nginx/sites-available/coop
    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        say "Обновляю nginx"
    else
        say "ВНИМАНИЕ: новый конфиг nginx не прошёл проверку, оставлен прежний"
        nginx -t || true
    fi
fi

if [ "${units_changed:-0}" = "1" ]; then
    systemctl daemon-reload
    systemctl restart coop-update.timer || true
fi

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

# Правки в static/ — это стили, скрипты и шаблоны браузера. Базы они не
# касаются, и обновлять ради них модули незачем: обновление останавливает
# службу на десятки секунд, а перезапуск занимает секунды. При выкладке
# раз в минуту разница видна невооружённым глазом.
if [ -n "$changed" ] && ! run git diff --name-only "$before" "$after" | grep -qv '/static/'; then
    say "Изменения только в static — обновление модулей не нужно"
    changed=""
fi

if [ -z "$changed" ]; then
    say "Изменения вне модулей — только перезапуск"
else
    say "Обновляю: $changed"
    systemctl stop coop-odoo
    run "$ODOO_HOME/venv/bin/python" "$ODOO_HOME/odoo/odoo-bin" \
        -c "$CONF" -d "$DB" -u "$changed" --stop-after-init --no-http
fi

# Собранные пакеты больше не сносим.
#
# Раньше здесь стояло удаление всех вложений /web/assets/%, «чтобы участник
# не получил старый файл по новому коду». Цену этого видно в логе: сборка
# web.assets_web.min.js занимает 12 секунд, css — шесть, и их платил тот,
# кто зашёл первым. При обновлении раз в минуту это стало бы постоянным
# налогом на каждого.
#
# Сносить не нужно: адрес пакета Odoo считает от содержимого файлов, и
# при изменённом scss он и так становится другим. В памяти процесса
# оставался только старый адрес — его снимает перезапуск ниже.
# Пересоберётся ровно то, что изменилось: правка стилей не тянет
# за собой пересборку семи мегабайт скриптов.

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

#!/usr/bin/env bash
# Прогреть пакеты стилей и скриптов.
#
#   bash warmup.sh [адрес]
#
# Odoo собирает пакеты при первом обращении и складывает результат в
# базу. Сборка стоит секунд десять, и без прогрева их платит тот, кто
# зашёл первым — на пустой белой странице. Поэтому после каждой сборки
# ассетов (обновление модулей, сброс пакетов) их запрашивают заранее, и
# делает это не человек, а сценарий.
#
# Запрашиваем именно те адреса, что стоят в разметке: пакет собирается
# на обращение к нему, а не к странице, которая на него ссылается.
set -u
BASE="${1:-http://127.0.0.1:8069}"
started=$(date +%s)

# Пакеты бэкенда — отдельным списком, и вот почему. Сценарий собирал
# адреса со страниц, но /odoo без входа отдаёт форму логина, а значит
# самый тяжёлый пакет — web.assets_web, семь мегабайт скриптов — не
# прогревался никогда. В логе его сборка занимает двенадцать секунд,
# и платил их первый вошедший участник, глядя на пустую страницу.
# Сами адреса ассетов вход не требуют, поэтому запросить их можно прямо.
for asset in /web/assets/any/web.assets_web.min.js              /web/assets/any/web.assets_web.min.css              /web/assets/any/web.assets_web_print.min.css; do
    seconds=$(curl -s -o /dev/null -w '%{time_total}' --max-time 300         "$BASE$asset" || echo '—')
    printf '  %-56s %s с
' "$(basename "$asset")" "$seconds"
done

for page in /web/login /odoo; do
    html=$(curl -s --max-time 120 "$BASE$page" || true)
    printf '%s' "$html" | grep -oE '/web/assets/[^"]+\.(js|css)' | sort -u \
    | while read -r asset; do
        seconds=$(curl -s -o /dev/null -w '%{time_total}' --max-time 300 \
            "$BASE$asset" || echo '—')
        printf '  %-56s %s с\n' "$(basename "$asset")" "$seconds"
    done
done

echo "Прогрев занял $(( $(date +%s) - started )) с"

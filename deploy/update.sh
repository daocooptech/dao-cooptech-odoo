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

BACKUP_DIR=/var/backups/coop
KEEP=7
LAST_DUMP=""

# Снимок базы в сжатом формате. Возвращает ложь, если не вышло: вызов
# решает сам, что с этим делать — перед обновлением это повод не
# обновляться, в суточном таймере повод написать в журнал.
backup_db() {
    mkdir -p "$BACKUP_DIR"
    chown postgres:postgres "$BACKUP_DIR" 2>/dev/null || true
    LAST_DUMP="$BACKUP_DIR/$DB-$(date +%F-%H%M%S).dump"
    say "Снимок базы → $LAST_DUMP"
    # От postgres, а не от root: у root нет роли в базе. Формат `-Fc`
    # сжатый, его понимает pg_restore в restore.sh.
    if sudo -u postgres pg_dump -Fc "$DB" > "$LAST_DUMP" 2>/dev/null; then
        # Пустой файл — это не снимок. Проверка дешёвая, а без неё
        # «копия есть» оказалось бы неправдой ровно тогда, когда она
        # понадобится.
        if [ -s "$LAST_DUMP" ]; then
            say "Снимок готов: $(du -h "$LAST_DUMP" | cut -f1)"
            # Храним последние семь. Считаем по времени изменения, а не
            # по имени: имя с датой удобно читать, но сортировать по нему
            # значит зависеть от формата даты.
            ls -1t "$BACKUP_DIR/$DB-"*.dump 2>/dev/null                 | tail -n +$((KEEP + 1)) | xargs -r rm -f
            return 0
        fi
    fi
    rm -f "$LAST_DUMP"
    LAST_DUMP=""
    return 1
}


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
for unit in coop-odoo.service coop-update.service coop-update.timer \
            coop-backup.service coop-backup.timer; do
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
# Зона кэша объявляется в контексте http, поэтому лежит отдельным
# файлом в conf.d. Каталог под кэш создаём сами: nginx создаёт его при
# старте, но только если у него хватает прав на родителя.
mkdir -p /var/cache/nginx/coop
chown -R www-data:www-data /var/cache/nginx/coop 2>/dev/null || true
nginx_changed=0
if ! cmp -s "$ODOO_HOME/coop-addons/deploy/nginx-cache.conf" /etc/nginx/conf.d/coop-cache.conf; then
    cp "$ODOO_HOME/coop-addons/deploy/nginx-cache.conf" /etc/nginx/conf.d/coop-cache.conf
    nginx_changed=1
fi
if ! cmp -s "$ODOO_HOME/coop-addons/deploy/nginx-coop.conf" /etc/nginx/sites-available/coop; then
    cp "$ODOO_HOME/coop-addons/deploy/nginx-coop.conf" /etc/nginx/sites-available/coop
    nginx_changed=1
fi
if [ "$nginx_changed" = "1" ]; then
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
    # Таймер снимков включается сам при первой же выкатке: заводить его
    # руками значит однажды забыть — и узнать об этом в тот день, когда
    # копия понадобится.
    systemctl enable --now coop-backup.timer || true
fi

if [ "$before" = "$after" ]; then
    say "Изменений нет ($after)"
    exit 0
fi

say "Обновление $before → $after"

# Какие модули задеты. Первый уровень каталогов и есть имена модулей.
#
# `if`, а не `[ -f … ] && echo`: при `set -e` и `pipefail` последняя
# проверка в цикле задаёт его код возврата, и папка без манифеста,
# оказавшаяся в списке последней, роняла всю выкатку. Так и вышло с
# `forks/`: правка README форков остановила обновление уже после
# `git reset` — код на сервере обновился, а модули нет, и следующий
# запуск изменений уже не видел.
changed=$(run git diff --name-only "$before" "$after" \
          | awk -F/ 'NF>1 {print $1}' | sort -u \
          | while read -r d; do
                if [ -f "$ODOO_HOME/coop-addons/$d/__manifest__.py" ]; then
                    echo "$d"
                fi
            done \
          | paste -sd, -)

# Правки в static/ — это стили, скрипты и шаблоны браузера. Базы они не
# касаются, и обновлять ради них модули незачем: обновление останавливает
# службу на десятки секунд, а перезапуск занимает секунды. При выкладке
# раз в минуту разница видна невооружённым глазом.
#
# Считаем в переменную, а не проверяем `grep -q` прямо в условии.
# Причина — 20 сентября 2026: в выкатке приехало 425 снимков и девять
# файлов кода, а сценарий отчитался «изменения только в static» и
# модули не тронул. `grep -q` выходит на первом же совпадении, git
# получает SIGPIPE, при `set -o pipefail` весь конвейер считается
# упавшим, и отрицание превращает «код изменился» в «изменений нет».
# Молча: в журнале осталась строка про static, и загрузчик данных не
# выполнялся вовсе.
не_static=$(run git diff --name-only "$before" "$after" \
            | grep -v '/static/' | head -1 || true)
if [ -n "$changed" ] && [ -z "$не_static" ]; then
    say "Изменения только в static — обновление модулей не нужно"
    changed=""
fi

# Новые модули: их надо не обновить, а поставить.
#
# `-u` ставит только то, что уже установлено; модуль, которого в базе нет,
# он молча пропускает. Отсюда 16 сентября 2026 вышло так: код `coop_settings`
# приехал на боевую, выкатка отчиталась «Готово», а раздела настроек на
# платформе не было — ставили руками.
#
# Ищем по папкам с манифестом, а не по списку в коде: список разошёлся бы
# с действительностью на первом же новом модуле. Спрашиваем базу напрямую
# (`psql` от имени odoo), потому что поднимать реестр ради одного запроса
# дороже самого запроса.
new_modules=""
for d in "$ODOO_HOME"/coop-addons/coop_*/; do
    name=$(basename "$d")
    [ -f "$d/__manifest__.py" ] || continue
    state=$(run psql -d "$DB" -tAc         "select state from ir_module_module where name = '$name'" 2>/dev/null || echo '')
    # Пусто — модуля нет в списке вовсе (ещё не читали каталог модулей);
    # `uninstalled` — прочитали, но не ставили. И то и другое значит «поставить».
    case "$state" in
        installed|to\ upgrade) ;;
        *) new_modules="${new_modules:+$new_modules,}$name" ;;
    esac
done

if [ -n "$new_modules" ]; then
    say "Новые модули, ставлю: $new_modules"
    systemctl stop coop-odoo
    if ! run "$ODOO_HOME/venv/bin/python" "$ODOO_HOME/odoo/odoo-bin"             -c "$CONF" -d "$DB" -i "$new_modules" --stop-after-init --no-http; then
        say "УСТАНОВКА УПАЛА: $new_modules"
        systemctl start coop-odoo || true
        exit 1
    fi
    systemctl start coop-odoo
fi

if [ -z "$changed" ]; then
    say "Изменения вне модулей — только перезапуск"
else
    # Снимок базы до обновления.
    #
    # Резервной копии боевой базы не было вообще: `restore.sh` заливает
    # со стенда разработки, то есть восстановил бы девелоперские данные,
    # а не боевые. На боевой двести проектов, пятьсот сделок, тысяча
    # вкладов — недели работы, которые держались на одной копии.
    #
    # Снимок делается только перед обновлением модулей: правки стилей и
    # перезапуск базу не трогают, и копия на каждую выкладку заняла бы
    # диск без пользы. Суточная копия идёт отдельным таймером.
    #
    # Пункт 19 разбора архитектора.
    if backup_db; then
        snapshot="$LAST_DUMP"
    else
        say "ВНИМАНИЕ: снимок базы не сделан — обновление отменено"
        exit 1
    fi

    say "Обновляю: $changed"
    systemctl stop coop-odoo
    # Код возврата обновления ловим сами: при `set -e` сценарий вышел бы
    # молча, не сказав, откуда откатываться. Тринадцатого сентября
    # обновление уже роняло загрузку реестра целиком, оставив в базе
    # двадцать семь адресов из сорока семи, и код возврата был нулевой.
    if ! run "$ODOO_HOME/venv/bin/python" "$ODOO_HOME/odoo/odoo-bin"             -c "$CONF" -d "$DB" -u "$changed" --stop-after-init --no-http; then
        say "ОБНОВЛЕНИЕ УПАЛО. База могла остаться в половинчатом виде."
        say "Откат: bash $ODOO_HOME/coop-addons/deploy/restore.sh $snapshot"
        systemctl start coop-odoo || true
        exit 1
    fi
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

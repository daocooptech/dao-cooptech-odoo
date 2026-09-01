#!/usr/bin/env bash
# Сборка стенда ДАО КООПЕХ в Codespaces. Выполняется один раз при создании.
set -eu

STAND=/stand
WS=/workspace
DB=koopeh

echo "== Модули Rudoo =="
if [ ! -d "$STAND/rudoo-addons" ]; then
  git clone --depth 1 https://git.ruodoo.ru/ruodoo-public/public.git "$STAND/rudoo-addons"
fi

echo "== Зависимости =="
# Внешние зависимости модулей Rudoo. weasyprint не ставим: он тянет
# библиотеки GTK, а печать на стенде не главное.
pip install --quiet --break-system-packages \
  beautifulsoup4 "dadata==21.10.1" docxcompose docxtpl num2words polib \
  pytils siphashc pymorphy3 || true

# Совместимость: l10n_ru_contract импортирует pymorphy2, который на
# Python 3.11+ не работает — внутри вызывает удалённый inspect.getargspec.
# Преемник pymorphy3 совместим по интерфейсу; заглушка избавляет от правки
# чужого модуля, которая не пережила бы обновление дистрибутива.
SITE=$(python3 -c "import site; print(site.getsitepackages()[0])")
mkdir -p "$SITE/pymorphy2"
cat > "$SITE/pymorphy2/__init__.py" <<'PY'
"""Совместимость: pymorphy2 -> pymorphy3. См. vendor/README.md."""
from pymorphy3 import *          # noqa: F401,F403
from pymorphy3 import MorphAnalyzer   # noqa: F401
PY

echo "== Конфигурация =="
cat > "$STAND/odoo.conf" <<EOF
[options]
; Порядок важен: сначала наши модули, потом форки, потом Rudoo, потом ядро.
; При совпадении имён наше перекрывает чужое, а не наоборот.
addons_path = $WS,$WS/forks,$STAND/rudoo-addons,/usr/lib/python3/dist-packages/odoo/addons
data_dir = /var/lib/odoo
db_host = db
db_port = 5432
db_user = odoo
db_password = odoo
db_name = $DB
http_port = 8069
http_interface = 0.0.0.0
workers = 0
admin_passwd = koopeh-stand
without_demo = all
EOF

ODOO="odoo -c $STAND/odoo.conf"

echo "== 1. Чистая база, без демо-данных Odoo =="
$ODOO -d "$DB" -i base --without-demo=all --stop-after-init

echo "== 2. Рубль и Россия — до бухгалтерии =="
# Порядок принципиален: Odoo не даёт менять валюту компании, когда по ней
# уже есть проводки, а установка бухгалтерии сбрасывает её обратно. Значит
# рубль ставится до первой проводки, иначе позже это уже не исправить.
$ODOO shell -d "$DB" --no-http <<'PY'
rub = env['res.currency'].with_context(active_test=False).search([('name', '=', 'RUB')], limit=1)
rub.active = True
ru = env['res.country'].search([('code', '=', 'RU')], limit=1)
env.company.write({'currency_id': rub.id, 'country_id': ru.id,
                   'name': 'ДАО КООПЕХ — рабочая группа'})
env.cr.commit()
print('валюта:', env.company.currency_id.name, '| страна:', env.company.country_id.code)
PY

echo "== 3. План счетов по приказу 94н =="
$ODOO -d "$DB" -i account,l10n_ru --without-demo=all --stop-after-init

echo "== 4. Разделы МВП =="
$ODOO -d "$DB" --without-demo=all --stop-after-init \
  -i contacts,hr,hr_skills,hr_recruitment,project,hr_timesheet,stock,sale_management,purchase,portal,website,website_forum,website_slides,event

echo "== 5. Модули Rudoo =="
$ODOO -d "$DB" --without-demo=all --stop-after-init \
  -i l10n_ru_base,l10n_ru_contract,l10n_ru_act_rev,l10n_ru_advance_payments,l10n_ru_doc,l10n_ru_upd_xml,dms,base_tier_validation,base_user_role,dadata_connector,web_debranding,website_debranding,portal_debranding

echo "== 6. Наши модули =="
$ODOO -d "$DB" --without-demo=all --stop-after-init \
  -i coop_theme,coop_base,coop_people,coop_orgs,coop_resources,coop_tokens,coop_bounty,coop_website,coop_extensions,coop_demo

echo "== 7. Русский язык =="
$ODOO -d "$DB" --load-language=ru_RU -i translation_helper --stop-after-init
$ODOO shell -d "$DB" --no-http <<'PY'
env['res.lang'].with_context(active_test=False).search([('code', '=', 'ru_RU')]).active = True
env['res.users'].search([]).write({'lang': 'ru_RU', 'tz': 'Europe/Moscow'})
env['res.partner'].search([]).write({'lang': 'ru_RU'})
tpl = env.ref('base.default_user', raise_if_not_found=False)
if tpl:
    tpl.sudo().write({'lang': 'ru_RU', 'tz': 'Europe/Moscow'})

# Пайщик с учётной записью: под ним видно правила доступа в работе, а под
# администратором платформы членство не видно вовсе — и это правильно.
board = env.ref('coop_base.group_coop_board')
if not env['res.users'].search([('login', '=', 'vodyanov')], limit=1):
    env['res.users'].create({
        'name': 'Водянов Алексей Петрович',
        'login': 'vodyanov',
        'password': 'vodyanov',
        'partner_id': env.ref('coop_demo.person_vodyanov').id,
        'group_ids': [(4, env.ref('base.group_user').id), (4, board.id)],
        'lang': 'ru_RU',
        'tz': 'Europe/Moscow',
    })
env.cr.commit()
print('готово: счетов в плане —', env['account.account'].search_count([]))
PY

echo "== Стенд собран. Вход: admin/admin или vodyanov/vodyanov =="

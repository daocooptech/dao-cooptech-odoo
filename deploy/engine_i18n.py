# -*- coding: utf-8 -*-
"""Перезалить в базу русский перевод модулей, у которых он сменился в движке.

Запускается из update.sh при смене движка, через `odoo-bin shell`; список
модулей update.sh кладёт в `/tmp/coop_engine_i18n.txt`.

Зачем. Строки из кода (Python, JavaScript) движок берёт из `.po` на лету,
а подписи полей, меню, фильтров и пояснения действий хранятся в базе и при
обычном обновлении модуля не перезаписываются. Правка `ru.po` в форке
(7.10 — меню base, digest…; 8.10 — CRM «Лид/Возможность» → «Обращение»)
без этого шага до экрана не доходила.

Переименования меню платформой (`coop.menu.order`: «Обсуждения» →
«Сообщения» и др.) перезапись затирает — поэтому они применяются заново.
"""
path = '/tmp/coop_engine_i18n.txt'
with open(path, encoding='utf-8') as handle:
    wanted = handle.read().split()
Module = env['ir.module.module']
names = Module.search([('name', 'in', wanted), ('state', '=', 'installed')]).mapped('name')
if names:
    Module._load_module_terms(names, ['ru_RU'], overwrite=True)
    if 'coop.menu.order' in env:
        env['coop.menu.order'].apply()
    env.cr.commit()
print('Перевод перезалит: %s' % (', '.join(names) or 'нечего'))

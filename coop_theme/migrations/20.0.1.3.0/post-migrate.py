# -*- coding: utf-8 -*-
"""Значки разделов в уже собранных панелях — с Font Awesome на Material Symbols.

В Odoo 20 Font Awesome из ядра убран (решение 445 п. 18): класс `fa-users`
больше ничего не рисует, а значок задаётся именем Material Symbols в
`data-icon`. Список разделов в коде уже переведён, но панель у каждого
участника своя и хранит значок записью: без этого прохода у заведённых
в меню стояли бы пустые места.

Имя, которого в таблице нет (участник мог вписать своё), заменяется
нейтральным кружком: незнакомое имя шрифт выводит буквами, и «fa-…»
встало бы в меню текстом.
"""
import logging

_logger = logging.getLogger(__name__)

ICONS = {
    'fa-archive': 'archive',
    'fa-bar-chart': 'bar_chart',
    'fa-book': 'book',
    'fa-briefcase': 'work',
    'fa-bullseye': 'crisis_alert',
    'fa-calendar': 'calendar_today',
    'fa-certificate': 'verified',
    'fa-cog': 'settings',
    'fa-comments': 'forum',
    'fa-comments-o': 'chat_bubble',
    'fa-credit-card': 'credit_card',
    'fa-cube': 'deployed_code',
    'fa-database': 'database',
    'fa-diamond': 'diamond',
    'fa-exchange': 'swap_horiz',
    'fa-file-text-o': 'article',
    'fa-folder-open-o': 'folder_open',
    'fa-gavel': 'gavel',
    'fa-globe': 'public',
    'fa-graduation-cap': 'school',
    'fa-handshake-o': 'handshake',
    'fa-history': 'history',
    'fa-id-card-o': 'badge',
    'fa-lightbulb-o': 'lightbulb',
    'fa-microchip': 'memory',
    'fa-retweet': 'repeat',
    'fa-rocket': 'rocket_launch',
    'fa-shield': 'security',
    'fa-shopping-basket': 'shopping_basket',
    'fa-tasks': 'checklist',
    'fa-university': 'account_balance',
    'fa-user-circle-o': 'account_circle',
    'fa-users': 'group',
    'fa-wrench': 'build',
}
FALLBACK = 'circle'


def migrate(cr, version):
    if not version:
        return
    cr.execute("SELECT id, icon FROM coop_sidebar_item WHERE icon LIKE 'fa-%%'")
    rows = cr.fetchall()
    for item_id, icon in rows:
        cr.execute("UPDATE coop_sidebar_item SET icon = %s WHERE id = %s",
                   (ICONS.get(icon, FALLBACK), item_id))
    unknown = sorted({icon for _id, icon in rows if icon not in ICONS})
    _logger.info('Панель: значки переведены на Material Symbols — %s пунктов%s',
                 len(rows), f'; незнакомые: {unknown}' if unknown else '')

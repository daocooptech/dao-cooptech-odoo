# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — основа',
    'summary': 'Членство в кооперативе, роли и права',
    'description': """
Базовый модуль платформы ДАО КООПТЕХ.

Здесь только то, чего в Odoo нет по смыслу: членство в кооперативе. Это не
трудовые отношения (`hr.employee`) и не контакт (`res.partner`) — это
участие в организации, основанной на членстве, с паем, голосом на собрании
и своим порядком выхода.

Всё остальное берётся из стандарта и из дистрибутива Rudoo, а не пишется
заново. Карта соответствия — `docs/odoo-map.md` в репозитории прототипа.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://github.com/daocooptech/dao-cooptech',
    'category': 'Cooperative',
    'version': '20.0.1.1.0',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',          # лента объекта и подписчики — наш «журнал» из прототипа
    ],
    'data': [
        'security/coop_groups.xml',
        'data/coop_powers.xml',
        'data/coop_membership_powers.xml',
        'data/coop_legal_forms.xml',
        'data/coop_membership_roles.xml',
        'data/coop_setup.xml',
        'views/coop_membership_views.xml',
        'views/coop_verification_views.xml',
        'views/coop_notification_views.xml',
        'views/coop_contacts_views.xml',
        'views/coop_menus.xml',
        'data/coop_menu_order.xml',
        'security/ir.access.csv',
    ],
    'installable': True,
    'application': True,
}

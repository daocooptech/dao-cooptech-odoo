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
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',          # лента объекта и подписчики — наш «журнал» из прототипа
    ],
    'data': [
        'data/coop_security_unfreeze.xml',
        'security/coop_groups.xml',
        'data/coop_powers.xml',
        'data/coop_membership_powers.xml',
        'data/coop_legal_forms.xml',
        'data/coop_setup.xml',
        'security/ir.model.access.csv',
        'security/coop_verification_rules.xml',
        'views/coop_membership_views.xml',
        'views/coop_verification_views.xml',
        'views/coop_menus.xml',
        'data/coop_menu_order.xml',
    ],
    'installable': True,
    'application': True,
}

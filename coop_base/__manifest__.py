# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — основа',
    'summary': 'Членство в кооперативе, роли и права',
    'description': """
Базовый модуль платформы ДАО КООПЕХ.

Здесь только то, чего в Odoo нет по смыслу: членство в кооперативе. Это не
трудовые отношения (`hr.employee`) и не контакт (`res.partner`) — это
участие в организации, основанной на членстве, с паем, голосом на собрании
и своим порядком выхода.

Всё остальное берётся из стандарта и из дистрибутива Rudoo, а не пишется
заново. Карта соответствия — `docs/odoo-map.md` в репозитории прототипа.
""",
    'author': 'ДАО КООПЕХ',
    'website': 'https://github.com/daocooptech/dao-cooptech',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',          # лента объекта и подписчики — наш «журнал» из прототипа
    ],
    'data': [
        'security/coop_groups.xml',
        'security/ir.model.access.csv',
        'views/coop_membership_views.xml',
        'views/coop_menus.xml',
    ],
    'installable': True,
    'application': True,
}

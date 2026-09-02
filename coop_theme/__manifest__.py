# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — оформление',
    'summary': 'Палитра, шрифты и скругления платформы в интерфейсе Odoo',
    'description': """
Тема платформы для интерфейса Odoo.

Основное сделано переменными оформления, а не перекрытием готовых правил
селекторами: Odoo собирает интерфейс из переменных, и менять надо их —
перекрытия ломаются на каждом обновлении, переменные переживают его.

Трогается оформление, не раскладка. Переставлять элементы чужого
интерфейса — значит ломать привычки тех, кто уже работает в Odoo, и брать
на себя починку после каждого обновления.

Шрифты локальные и лежат в модуле: узел кооператива может стоять в сети
без выхода наружу, и интерфейс не должен от этого разъезжаться.
""",
    'author': 'ДАО КООПЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'coop_theme/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'coop_theme/static/src/scss/fonts.scss',
            'coop_theme/static/src/scss/backend.scss',
            'coop_theme/static/src/scss/catalog_view.scss',
            'coop_theme/static/src/scss/shell.scss',
            'coop_theme/static/src/js/catalog_view.js',
            'coop_theme/static/src/js/shell.js',
            'coop_theme/static/src/xml/catalog_view.xml',
            'coop_theme/static/src/xml/shell.xml',
        ],
        'web.assets_frontend': [
            'coop_theme/static/src/scss/fonts.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
}

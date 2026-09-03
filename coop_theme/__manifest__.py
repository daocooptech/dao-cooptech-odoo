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
    # `mail` в зависимостях не ради моделей, а ради порядка загрузки:
    # ленту в правую колонку уводит сам почтовый модуль, и наша
    # правка должна применяться после его собственной — иначе она
    # молча затирается.
    'depends': ['web', 'mail', 'coop_base'],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_sidebar_rules.xml',
        'views/coop_sidebar_views.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'coop_theme/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'coop_theme/static/src/scss/fonts.scss',
            'coop_theme/static/src/scss/backend.scss',
            'coop_theme/static/src/scss/dark.scss',
            'coop_theme/static/src/scss/catalog_view.scss',
            'coop_theme/static/src/scss/shell.scss',
            'coop_theme/static/src/js/catalog_sort.js',
            'coop_theme/static/src/js/catalog_map.js',
            'coop_theme/static/src/xml/catalog_map.xml',
            'coop_theme/static/src/js/catalog_filters.js',
            'coop_theme/static/src/xml/catalog_filters.xml',
            'coop_theme/static/src/scss/catalog_filters.scss',
            'coop_theme/static/src/js/catalog_view.js',
            'coop_theme/static/src/js/shell.js',
            'coop_theme/static/src/js/theme_switch.js',
            'coop_theme/static/src/js/wall.js',
            'coop_theme/static/src/js/bands.js',
            'coop_theme/static/src/scss/wall.scss',
            'coop_theme/static/src/xml/theme_switch.xml',
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

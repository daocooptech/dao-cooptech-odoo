# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — каталог расширений',
    'summary': 'Витрина расширений: установленные и общий каталог',
    'description': """
Каталог расширений платформы.

Витрина над штатным списком приложений Odoo, а не его замена. Технически
расширение остаётся обычным модулем, и кнопка «Подключить» ставит именно
его. Витрина нужна затем, что штатный список говорит на языке
разработчика — технические имена, зависимости, версии, — а кооператору
надо понимать, что он получит и во сколько это обойдётся.

Два раздела: установленные и общий каталог. Сторонний разработчик
публикует своё расширение и сам назначает условия: бесплатно, помесячно,
за год или единовременно навсегда.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'coop_base'],
    'data': [
        'security/ir.model.access.csv',
        'views/coop_extension_views.xml',
        'views/coop_extension_menus.xml',
        'data/coop_extension_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_extensions/static/src/scss/coop_extensions.scss',
        ],
    },
    'installable': True,
    'application': True,
}

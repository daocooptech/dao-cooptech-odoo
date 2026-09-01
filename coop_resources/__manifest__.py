# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — ресурсы',
    'summary': 'Каталог ресурсов: предложения и спрос, способы передачи, продвижение',
    'description': """
Каталог ресурсов платформы: что участники предлагают и что ищут.

Собственная модель, а не товар Odoo (решение владельца от 2026-09-01):
половина каталога — это «ищу» и «отдам даром», а товар по определению то,
что продают. Плата за это решение известна: связь со складом и со
сделками придётся заводить руками.

Продвижение объявления оплачивается токенами платформы и устроено
ставкой, как в контекстной рекламе: место в выдаче стоит столько, во
сколько его оценивают сами участники.
""",
    'author': 'ДАО КООПЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_tokens', 'coop_theme', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/coop_resource_methods.xml',
        'data/coop_promotion_setup.xml',
        'data/coop_resource_cron.xml',
        'views/coop_resource_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_resources/static/src/scss/coop_resources.scss',
        ],
    },
    'installable': True,
    'application': True,
}

# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — склад',
    'summary': 'Склады кооператива, зоны хранения и биржа свободных мощностей',
    'description': """
Склад у кооператива почти всегда наполовину пуст: сезон кончился, партия
уехала, морозильник держат ради двух месяцев в году. Соседу в это же
время место нужно — и он строит своё.

Раздел показывает склад как ресурс платформы и даёт выставить свободные
мощности другим участникам: в аренду, на ответственное хранение, в обмен
или под участие в проекте. Договорённость становится обычной сделкой
платформы — с реестром, перепиской и взаимными отзывами.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_orgs', 'coop_deals', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_warehouse_rules.xml',
        'views/coop_warehouse_views.xml',
        'views/coop_warehouse_offer_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_warehouse/static/src/scss/coop_warehouse.scss',
        ],
    },
    'installable': True,
}

# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — совместные закупки',
    'summary': 'Оптовая цена в складчину: сбор заказов, стоп, довоз, раздача',
    'description': """
Совместная закупка — это способ получить оптовую цену, не будучи оптовым
покупателем. Организатор находит поставщика и минимальный объём выкупа,
участники набирают его вскладчину, цена падает по уровням по мере набора.

Три вехи: «стоп» закрывает сбор заказов, «довоз» — товар пришёл
организатору, «раздача» — участники забирают своё в точке самовывоза.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_orgs', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/coop_groupbuy_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_groupbuy/static/src/scss/coop_groupbuy.scss',
        ],
    },
    'installable': True,
}

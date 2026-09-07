# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — аукционы',
    'summary': 'Торги на повышение и редукцион: излишки, подряды, техника',
    'description': """
Аукцион нужен там, где цена неизвестна заранее. Кооператив продаёт
излишки урожая или ненужную технику — цену назначает торг; кооператив
ищет подрядчика — цену сбивает редукцион.

Ставка в последние минуты продлевает торг. Без этого выигрывает не тот,
кто больше готов заплатить, а тот, у кого лучше связь и быстрее рука.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_resources', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/coop_auction_cron.xml',
        'views/coop_auction_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_auctions/static/src/scss/coop_auctions.scss',
        ],
    },
    'installable': True,
}

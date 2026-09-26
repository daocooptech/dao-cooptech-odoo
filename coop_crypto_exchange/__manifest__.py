# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — DEX биржа',
    'summary': 'Доска объявлений: купить и продать цифровую валюту как '
               'имущество; платформа не сторона и не держит ни ключей, ни денег',
    'description': """
Решение 392: «мы делаем функционал биржи». Название раздела — «DEX
биржа» (владелец 25 сентября 2026). Разбор юриста (2.6): без
статусов законно работает только доска объявлений — участники публикуют
предложения, находят друг друга и рассчитываются сами; платформа сводит,
показывает доверие и историю и фиксирует состоявшийся обмен.

Правила интерфейса (разбор, 2.3) — в коде: обмен не связан ни со сделкой,
ни с ресурсом платформы (связка — притворная оплата); раздел только для
вошедших участников; ключей и средств платформа не держит; крупный объём —
предупреждение о подтверждении личности. На каждом экране: «Здесь
покупают и продают цифровую валюту как имущество. Расплачиваться
цифровой валютой за товары и услуги в России нельзя».
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.2.0',
    'license': 'LGPL-3',
    'depends': ['coop_matching', 'coop_base', 'coop_theme', 'coop_wallet', 'coop_projects', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_crypto_rules.xml',
        'views/coop_crypto_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_crypto_exchange/static/src/scss/coop_crypto.scss',
            'coop_crypto_exchange/static/src/scss/coop_dex.scss',
            'coop_crypto_exchange/static/src/js/dex_terminal.js',
            'coop_crypto_exchange/static/src/xml/dex_terminal.xml',
            'coop_crypto_exchange/static/src/js/dex_node.js',
            'coop_crypto_exchange/static/src/xml/dex_node.xml',
            'coop_crypto_exchange/static/src/js/dex_farm.js',
            'coop_crypto_exchange/static/src/xml/dex_farm.xml',
        ],
    },
    'post_init_hook': '_post_init',
    'installable': True,
}

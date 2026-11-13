# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — кошелёк',
    'summary': 'Фиатный и крипто-кошелёк, взаимный кредит, взаиморасчёты, паевой счёт',
    'description': """
Кошелёк участника собирается из того, кем он является.

Фиатный и крипто-кошелёк есть у всех. Паевой счёт появляется только у
члена кооператива — и отдельный на каждый кооператив: пай в каждом свой,
и выходят из них порознь.

Денег платформа не держит. Принимать чужие средства и переводить их по
команде — банковская операция, и на неё нужна лицензия. Здесь ведётся
учёт обязательств: кто кому сколько должен и что подтверждено полученным.

Сальдо по контрагентам не хранится, а считается из графиков платежей по
сделкам: вторая копия неизбежно разошлась бы с первой, и тогда непонятно,
какой цифре верить.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '20.0.1.2.3',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_tokens', 'coop_deals', 'mail'],
    'data': [
        'data/coop_networks.xml',
        'data/coop_settlement_methods.xml',
        'data/coop_currencies.xml',
        'data/coop_currency_cron.xml',
        'data/coop_network_cron.xml',
        'views/coop_wallet_views.xml',
        'views/coop_wallet_operation_views.xml',
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_wallet/static/src/scss/coop_wallet.scss',
            'coop_wallet/static/src/scss/currency_switch.scss',
            'coop_wallet/static/src/js/currency_switch.js',
            'coop_wallet/static/src/xml/currency_switch.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}

# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — аналитика',
    'summary': '«Моя панель»: личный конструктор из графиков и сводных таблиц платформы',
    'description': """
Решение 420, слой 1. «Аналитика» — «Моя панель» штатного модуля `board`:
каждый участник собирает свою страницу из видов платформы — графиков,
сводных таблиц, списков — вместе с их фильтрами и группировками («Добавить
на мою панель» в меню действий вида). Для этого у разделов — готовые
графики и сводные таблицы: сделки, деньги, вклады в проекты, биржа,
обучение. У кого панель ещё не настроена — панель по умолчанию из них же.

Следующие слои (решение 420): готовые дашборды, портфель участника,
прогноз и план.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['board', 'coop_theme', 'coop_deals', 'coop_wallet', 'coop_projects',
                'coop_crypto_exchange', 'coop_education'],
    'data': [
        'views/coop_analytics_views.xml',
        'data/coop_analytics_board.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_analytics/static/src/js/board_tabs.js',
            'coop_analytics/static/src/xml/board_tabs.xml',
        ],
    },
    'installable': True,
}

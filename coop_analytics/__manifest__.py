# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — аналитика',
    'summary': '«Моя панель» и готовые дашборды платформы',
    'description': """
Решение 420, слой 1. «Аналитика» — «Моя панель» штатного модуля `board`:
каждый участник собирает свою страницу из видов платформы — графиков,
сводных таблиц, списков — вместе с их фильтрами и группировками («Добавить
на мою панель» в меню действий вида). Для этого у разделов — готовые
графики и сводные таблицы: сделки, деньги, вклады в проекты, биржа,
обучение. У кого панель ещё не настроена — панель по умолчанию из них же.

Слой 2 — готовые дашборды на штатном `spreadsheet_dashboard`: «Мои деньги»,
«Мои сделки и доверие», «Проекты», «Биржа» — плитки к прошлому периоду,
графики, таблицы «топ-10», глобальные фильтры по периоду, городу, разделу.
Файлы дашбордов собирает `tools/build_dashboards.py`.

Слой 3 — «Портфель участника» (решения 421, 422), слой 4 — «Прогноз и план»:
свой тренд и план на месяц (решение 423).
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '20.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['board', 'spreadsheet_dashboard', 'coop_theme', 'coop_deals', 'coop_wallet',
                'coop_projects', 'coop_matching', 'coop_crypto_exchange', 'coop_tokenomics',
                'coop_digital_assets',
                'coop_education', 'coop_people', 'coop_profile', 'coop_wall'],
    'data': [
        'views/coop_analytics_views.xml',
        'data/coop_analytics_board.xml',
        'data/coop_analytics_dashboards.xml',
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_analytics/static/src/scss/coop_analytics.scss',
            'coop_analytics/static/src/js/board_tabs.js',
            'coop_analytics/static/src/xml/board_tabs.xml',
            'coop_analytics/static/src/scss/portfolio.scss',
            'coop_analytics/static/src/js/portfolio.js',
            'coop_analytics/static/src/xml/portfolio.xml',
            'coop_analytics/static/src/scss/forecast.scss',
            'coop_analytics/static/src/js/forecast.js',
            'coop_analytics/static/src/xml/forecast.xml',
        ],
        # Экран дашбордов грузится лениво, своим бандлом — вкладки над ним туда же.
        'spreadsheet.o_spreadsheet': [
            'coop_analytics/static/src/dashboards/dashboard_tabs.js',
            'coop_analytics/static/src/dashboards/dashboard_tabs.xml',
        ],
    },
    'installable': True,
}

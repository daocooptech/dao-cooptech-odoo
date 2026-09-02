# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — поиск по платформе',
    'summary': 'Поле поиска в шапке, ищущее сразу по всем каталогам',
    'description': """
Поиск в шапке — навигатор по платформе, а не каталог. Он отвечает на вопрос
«куда мне идти», и поэтому показывает по нескольку строк из каждого раздела,
а не длинный общий список.

Он не заменяет поиск внутри каталога и не заменяется им: тот ищет по одному
разделу с его фильтрами и порядком, этот — по всем сразу. Чтобы два поля на
одном экране не путали, у каждого своё место и своя подпись.

Сделки в общую выдачу попадают отдельной группой и только свои: чужая
сделка — не объект публичного каталога.
""",
    'author': 'ДАО КООПЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'coop_base', 'coop_theme', 'coop_people', 'coop_orgs', 'coop_skills',
        'coop_resources', 'coop_vacancies', 'coop_projects',
        'coop_communities', 'coop_deals',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_search/static/src/js/coop_search.js',
            'coop_search/static/src/xml/coop_search.xml',
            'coop_search/static/src/scss/coop_search.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
}

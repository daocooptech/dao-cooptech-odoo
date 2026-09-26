# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — образование',
    'summary': 'Курсы для участников на штатном eLearning Odoo: каталог полками по темам, мои курсы',
    'description': """
Решение 411: «Образование — стандартный модуль Odoo по курсам»
(eLearning, `website_slides`). Сами курсы, уроки, прохождение, тесты и
отзывы — штатные; здесь только то, чего у штатного модуля нет для
платформы: каталог курсов в общем виде каталогов (полки по темам, плитка
с обложкой, автором, числом уроков и учеников, оценкой и моим
прогрессом) и раздел «Образование» в левом меню.

Курс открывается на штатной странице курса — там уроки, прогресс и
отзывы.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['website_slides', 'coop_base', 'coop_theme'],
    'data': [
        'views/coop_education_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_education/static/src/scss/coop_education.scss',
        ],
    },
    'post_init_hook': '_post_init',
    'installable': True,
}

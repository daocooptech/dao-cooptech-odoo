# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — краудсорсинг',
    'summary': 'Задачи проектов за токены проекта; страница «Помощь проекту» нашего проекта',
    'description': """
Краудсорсинг для всех проектов платформы (решение 690): проект ставит
задачу, участники подают заявки, автор утверждает исполнителя и
принимает результат по критериям. Оплата — только токенами своего
проекта; экономику токена проект раскрывает сам, в рамках законов своей
страны. Наш проект — ДАО КООПТЕХ — платит токенами услуг платформы из
фонда задач.

«Краудсорсинг» в кабинете — подраздел «Проектов»: каталог проектов с
задачами и карточка проекта по краудсорсингу (токен, экономика токена,
задачи). «Помощь проекту» в подвале кабинета — карточка нашего проекта;
на сайте `/help-project` — его задачи и пожертвования.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '20.0.1.6.4',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_tokens', 'coop_theme', 'coop_orgs', 'coop_deals',
                'coop_profile', 'website', 'mail'],
    'data': [
        'security/coop_bounty_groups.xml',
        'data/coop_bounty_data.xml',
        'views/coop_bounty_views.xml',
        'views/coop_bounty_website.xml',
        'views/coop_bounty_task_page.xml',
        'views/coop_bounty_p2_views.xml',
        'views/coop_bounty_p2b_views.xml',
        'data/coop_bounty_p2b_data.xml',
        'security/ir.access.csv',
        'data/cooptech_tasks.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'coop_bounty/static/src/scss/bounty.scss',
        ],
        'web.assets_backend': [
            'coop_bounty/static/src/scss/backend_bounty.scss',
        ],
    },
    'installable': True,
    # Не приложение: «Помощь проекту» открывается ссылкой в подвале
    # (`/help-project`), а не пунктом меню; с `application` каталог
    # предлагал её «Подключить» в меню (владелец 20.10.2026).
    'application': False,
}

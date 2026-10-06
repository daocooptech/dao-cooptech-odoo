# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — лендинг и сайт',
    'summary': 'Публичная страница платформы, редактируемая конструктором сайта',
    'description': """
Лендинг платформы из прототипа (`index.html`), перенесённый на модуль
«Сайт» Odoo.

Содержимое лежит в блоках oe_structure, поэтому правится штатным
конструктором: текст, картинки и порядок секций меняются без правки кода.
Стили перенесены из прототипа и опираются на те же токены, что и весь
интерфейс, — лендинг и кабинет не расходятся по оформлению.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '20.0.2.0.0',
    'license': 'LGPL-3',
    # Лендинг считает живые цифры по участникам, специализациям и
    # правовым формам и ведёт в каталоги людей и организаций.
    # Без этих зависимостей главная падает при отдельной установке.
    'depends': ['website', 'auth_signup', 'mail', 'coop_theme', 'coop_base',
                'coop_people', 'coop_orgs'],
    'data': [
        'views/coop_landing.xml',
        'views/coop_footer.xml',
        'views/coop_contact_views.xml',
        'views/coop_legal.xml',
        'views/coop_signup.xml',
        'data/coop_website_lang.xml',
        'data/coop_website_setup.xml',
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_frontend': [
            'coop_website/static/src/scss/landing.scss',
        ],
    },
    'installable': True,
    'application': False,
}

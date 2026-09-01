# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — лендинг и сайт',
    'summary': 'Публичная страница платформы, редактируемая конструктором сайта',
    'description': """
Лендинг платформы из прототипа (`index.html`), перенесённый на модуль
«Сайт» Odoo.

Содержимое лежит в блоках oe_structure, поэтому правится штатным
конструктором: текст, картинки и порядок секций меняются без правки кода.
Стили перенесены из прототипа и опираются на те же токены, что и весь
интерфейс, — лендинг и кабинет не расходятся по оформлению.
""",
    'author': 'ДАО КООПЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['website', 'coop_theme'],
    'data': [
        'views/coop_landing.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'coop_website/static/src/scss/landing.scss',
        ],
    },
    'installable': True,
    'application': False,
}

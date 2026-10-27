# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — адреса объявлений',
    'summary': 'Точный адрес и точка на карте у каждого объявления',
    'description': """
Город говорит, где искать, но не куда ехать. Владелец 12.10.2026: «почему
не показывает точный адрес каждого объявления? только город, надо
исправить, смотри как сделано на авито».

Модуль добавляет объявлениям адрес (улица и дом) и его координаты. Адрес
человек пишет сам, координаты по нему находятся при сохранении (поиск
адресов OpenStreetMap). На карте каталога каждое объявление стоит своей
точкой.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '20.0.1.0.1',
    'license': 'LGPL-3',
    'depends': [
        'coop_base',
        'coop_auctions', 'coop_barter', 'coop_communities', 'coop_crypto_exchange',
        'coop_events', 'coop_groupbuy', 'coop_mining', 'coop_programs',
        'coop_projects', 'coop_resources', 'coop_skills', 'coop_vacancies',
        'coop_warehouse',
    ],
    'data': [
        'views/coop_geo_views.xml',
        'data/coop_geo_data.xml',
    ],
    'installable': True,
}

# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — события',
    'summary': 'Календарь кооперативной жизни: обучение, встречи, собрания, ярмарки',
    'description': """
Событие — единственное место платформы, где кооперация происходит лично.
Всё остальное — записи об уговорах; здесь люди встречаются, и от этого
зависит, состоится ли остальное.

Запись на событие — обязательство перед организатором: он считает места,
еду и стулья. Поэтому отмена видна и учитывается, а не проходит молча.
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_orgs', 'coop_communities', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/coop_event_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_events/static/src/scss/coop_events.scss',
        ],
    },
    'installable': True,
}

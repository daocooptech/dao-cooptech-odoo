# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — люди',
    'summary': 'Каталог участников: навыки, город, доверие, переписка',
    'description': """
Каталог людей платформы.

Не новая модель, а признак и несколько полей у контакта. Заводить второго
человека рядом с res.partner значит получить два справочника людей,
которые немедленно разъедутся: один для сделок, другой для каталога.

Две вещи разведены намеренно, как в макете: проверка личности и уровень
доверия. Подтверждённый паспорт говорит, кто человек; доверие — как он
исполняет обязательства. Ставить их рядом нельзя, иначе одно читается как
подтверждение другого.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_theme', 'contacts', 'hr_skills', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_people_rules.xml',
        'views/coop_people_views.xml',
        'data/coop_home.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_people/static/src/scss/coop_people.scss',
        ],
    },
    'installable': True,
    'application': True,
}

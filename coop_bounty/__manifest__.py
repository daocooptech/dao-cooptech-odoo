# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — помощь проекту',
    'summary': 'Краудсорсинг задач с вознаграждением в токенах и приём пожертвований',
    'description': """
Задачи рабочей группы, которые может взять любой участник платформы, и
страница «Помощь проекту» на публичной части.

Устроено как на бирже фриланса и по образцу баунти: менеджер сообщества
публикует задачу с вознаграждением, участники подают заявки, менеджер
утверждает исполнителя и принимает работу. Токены зачисляются в кошелёк
исполнителя при приёмке — не раньше: между «я сделал» и «работа принята»
помещается всё, ради чего приёмка и нужна.

Вознаграждение — токенами платформы, а не деньгами. Это принципиально:
денежная выплата за выполненную работу означала бы трудовые или
подрядные отношения со всеми вытекающими обязанностями, а токен —
внутренняя единица платформы (см. coop_tokens).
""",
    'author': 'ДАО КООПЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_tokens', 'coop_theme', 'website', 'mail'],
    'data': [
        'security/coop_bounty_groups.xml',
        'security/ir.model.access.csv',
        'security/coop_bounty_rules.xml',
        'views/coop_bounty_views.xml',
        'views/coop_bounty_website.xml',
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
    'application': True,
}

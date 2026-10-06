# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — проекты (краудресурсинг)',
    'summary': 'Проекты, которые собирают не только деньги, но труд, технику и материалы',
    'description': """
Краудресурсинг — следующая ступень после краудинвестинга.

Разница в том, чем скидываются. В краудфандинге и краудинвестинге — только
деньгами; здесь — чем угодно, что имеет стоимость: трудом, техникой,
материалами, помещением, знаниями, деньгами.

Отсюда всё устройство раздела. Доля участника не вписывается руками, а
складывается: его вклад, делённый на сумму всех вкладов. Иначе смену
экскаваторщика и перевод на счёт не свести в одну величину, и
«коллективный проект» распадётся на инвесторов и наёмных.

Управление проектом здесь не ведётся: для этого есть штатный модуль Odoo,
и он подключается, когда проект собран и запущен.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '20.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_resources', 'project', 'mail'],
    'data': [
        'security/coop_project_groups.xml',
        'views/coop_project_views.xml',
        'views/coop_project_need_views.xml',
        'data/coop_project_backfill.xml',
        'data/coop_project_readiness.xml',
        'data/coop_project_cron.xml',
        'data/project_stage_data.xml',
        'security/ir.access.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_projects/static/src/scss/coop_projects.scss',
            'coop_projects/static/src/js/readiness_ring.js',
            'coop_projects/static/src/xml/readiness_ring.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
}

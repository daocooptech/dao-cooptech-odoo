# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — данные для проверки',
    'summary': 'Немного данных в разделы МВП, чтобы экраны не были пустыми',
    'description': """
Небольшой набор данных в разделы платформы: ресурсы, проект, навыки,
сделка. Взяты из прототипа — так стенд и макет говорят об одних и тех же
вещах, и расхождение между нарисованным и работающим видно сразу.

Это demo-данные: при установке без демо-режима они не ставятся и в боевую
базу не попадают.
""",
    'author': 'ДАО КООПЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_people', 'coop_orgs', 'coop_resources', 'coop_skills', 'coop_vacancies', 'coop_projects', 'coop_communities', 'coop_deals', 'coop_wallet', 'coop_bounty', 'product', 'project', 'hr_skills', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'data/coop_admin_rights.xml',
        'data/coop_reference_data.xml',
        'data/coop_demo_data.xml',
        'data/coop_people_data.xml',
        'data/coop_load.xml',
    ],
    'installable': True,
}

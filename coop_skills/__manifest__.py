# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — навыки',
    'summary': 'Каталог предложений навыка: кто что умеет и на каких условиях',
    'description': """
Каталог навыков платформы — то, что участники готовы делать за
вознаграждение.

Это не справочник умений и не вакансия. Вакансию размещает тот, кому
нужна работа; предложение навыка — тот, кто готов работать. Стороны
разные, и смешивать их в одном списке нельзя.

У одного человека предложений может быть несколько — по числу
специализаций, как несколько резюме. Одно на человека означало бы, что
мастер с двумя ремёслами обязан выбрать, каким из них он «на самом деле»
занимается.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_people', 'coop_theme', 'hr_skills', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_skills_rules.xml',
        'views/coop_skill_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_skills/static/src/scss/coop_skills.scss',
        ],
    },
    'installable': True,
    'application': True,
}

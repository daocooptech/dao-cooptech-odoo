# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПЕХ — моя страница',
    'summary': 'Профиль участника и всё, что у него есть на платформе',
    'description': """
«Моя страница» — не отдельная сущность, а тот же участник, открытый на себе.
Второй модели профиля рядом с контактом здесь нет намеренно: карточка
человека в каталоге и своя страница разъедутся за пару месяцев, если это
будут две формы.

Разница между «моей страницей» и карточкой того же человека глазами
постороннего выражена признаком «это я» и правами: владельцу видны заявки,
черновики, снятые с публикации объявления и непринятые роли; постороннему —
только то, что человек опубликовал.

Раздел сводит владения из всех каталогов, поэтому модуль стоит поверх них:
навыки, ресурсы, проекты, сообщества, вакансии, сделки, членство в
организациях.
""",
    'author': 'ДАО КООПЕХ',
    'category': 'Cooperative',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'coop_base', 'coop_theme', 'coop_people', 'coop_skills',
        'coop_resources', 'coop_vacancies', 'coop_projects',
        'coop_communities', 'coop_deals', 'coop_wallet', 'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_profile_rules.xml',
        'views/coop_profile_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_profile/static/src/scss/coop_profile.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
}

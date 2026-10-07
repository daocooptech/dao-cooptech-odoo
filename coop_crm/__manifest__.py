{
    'name': 'ДАО КООПТЕХ - CRM организаций',
    'summary': 'Лиды организации и превращение лида в сделку площадки',
    'description': """
Решение 450 (07.10.2026): как в Битрикс24 — «Лид -> сделка площадки».

* У организации в её компании учёта - отдел продаж; лиды ведут держатели
  полномочия «Сделки» (бухгалтерия им при этом не открывается).
* Кнопка «Создать сделку» превращает лид в сделку площадки (стадия
  «Переговоры»), лид отмечается выигранным; сделка помнит свой лид.
""",
    'author': 'ДАО КООПТЕХ',
    'category': 'Cooperative',
    'version': '20.0.1.2.0',
    'license': 'LGPL-3',
    'depends': ['crm', 'stock', 'project', 'hr', 'coop_invoicing', 'coop_deals',
                'coop_profile'],
    'data': [
        'views/crm_lead_views.xml',
        'views/coop_deal_views.xml',
        'views/org_cabinet_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_crm/static/src/scss/coop_crm.scss',
            'coop_crm/static/src/js/autosave_toggle.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
}

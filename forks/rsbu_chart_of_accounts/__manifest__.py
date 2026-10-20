# -*- coding: utf-8 -*-
{
    'name': 'РСБУ — План счетов',
    'version': '20.0.2026.10.20',
    'summary': 'План счетов бухгалтерского учёта РСБУ (Приказ Минфина № 94н)',
    'description': """
РСБУ — План счетов
==================

Независимый от account.account иерархический план счетов РСБУ по Приказу
Минфина России № 94н. Базовый фундамент РСБУ-слоя.

Возможности:
------------
* Иерархия счетов произвольной глубины
* Признак счёта: активный / пассивный / активно-пассивный / забалансовый
* Флаги обязательных субконто (partner / product / user / employee)
* Методы агрегации сумм и сальдо по дереву субсчетов
* Типовой план счетов 94н как предустановленные данные
* Мультикомпанийность (свой план на каждую компанию)

Нативная бухгалтерия Odoo не затрагивается.
    """,
    'author': 'MK.Lab, RuOdoo',
    'website': 'https://ruodoo.ru',
    'category': 'Accounting/Localizations',
    'depends': ['base', 'mail'],
    'data': [
        'security/rsbu_security.xml',
        'wizards/rsbu_account_load_wizard_views.xml',
        'views/rsbu_account_views.xml',
        'views/rsbu_menus.xml',
        'security/ir.access.csv',
    ],
    'post_init_hook': 'post_init_load_chart',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'maintainers': ['mklab', 'ruodoo'],
}

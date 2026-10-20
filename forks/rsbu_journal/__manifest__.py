# -*- coding: utf-8 -*-
{
    'name': 'РСБУ — Журнал хозяйственных операций',
    'version': '20.0.2026.09.17',
    'summary': 'Журнал операций РСБУ (двойная запись, субконто)',
    'description': """
РСБУ — Журнал хозяйственных операций
====================================

Журнал бухгалтерских проводок по российским стандартам (РСБУ) —
ядро РСБУ-слоя. Ведёт двойную запись по плану счетов 94н.

Возможности:
------------
* Проводки по методу двойной записи (дебет / кредит).
* Аналитика (субконто) в разрезе контрагентов, товаров, пользователей
  и сотрудников.
* Контроль баланса проводки и обязательности заполнения субконто
  при проведении.
* Обороты и сальдо по счетам плана счетов рассчитываются из проведённых
  проводок журнала.

Учёт ведётся в рублях, поддерживается работа нескольких компаний в одной
базе. Нативная бухгалтерия Odoo не затрагивается.
    """,
    'author': 'MK.Lab, RuOdoo',
    'website': 'https://ruodoo.ru',
    'category': 'Accounting/Localizations',
    'depends': ['rsbu_chart_of_accounts', 'hr', 'product', 'l10n_ru_contract'],
    'data': [
        'security/rsbu_journal_security.xml',
        'data/ir_sequence_data.xml',
        'views/rsbu_move_views.xml',
        'wizards/rsbu_trial_balance_wizard_views.xml',
        'report/rsbu_trial_balance_templates.xml',
        'views/rsbu_menus.xml',
        'security/ir.access.csv',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'maintainers': ['mklab', 'ruodoo'],
}

# -*- coding: utf-8 -*-
{
    'name': 'РСБУ — Учёт НДС на УСН',
    'version': '19.0.2026.10.01',
    'summary': 'Счета-фактуры, книги продаж/покупок, декларация НДС',
    'description': """
РСБУ — Учёт НДС на УСН
======================

Учёт НДС для плательщиков УСН, которые обязаны исчислять налог.
НДС учитывается на основании счетов-фактур и проводок журнала РСБУ.

Возможности:
------------
* Настройка ставки НДС: освобождён, 5% или 7%.
* Счета-фактуры: авансовые, отгрузочные и корректировочные.
* Книга продаж и книга покупок формируются из проводок НДС.
* Свод итогов по НДС и расчёт суммы декларации за период.
* Пересчёт данных за выбранный период.

Как пользоваться:
-----------------
1. Укажите ставку НДС в настройках.
2. Оформляйте счета-фактуры к операциям реализации и поступления.
3. Книги продаж и покупок и итоговые суммы для декларации
   рассчитываются автоматически; при необходимости пересчитайте
   их за нужный период.
    """,
    'author': 'MK.Lab, RuOdoo',
    'website': 'https://ruodoo.ru',
    'category': 'Accounting/Localizations',
    'depends': ['rsbu_kudir'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'wizards/rsbu_vat_recompute_wizard_views.xml',
        'wizards/rsbu_vat_declaration_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/rsbu_invoice_views.xml',
        'views/rsbu_realization_views.xml',
        'views/rsbu_vat_book_views.xml',
        'views/rsbu_vat_summary_views.xml',
        'views/rsbu_period_close_views.xml',
        'views/rsbu_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'maintainers': ['mklab', 'ruodoo'],
}

# -*- coding: utf-8 -*-
{
    'name': "Российская локализация - Документы",

    'summary': "Первичные документы",

    'description': """
Российская локализация — Документы
==================================

Печатные формы первичных документов в соответствии с законодательством
России.

Возможности:

* Товарная накладная (ТОРГ-12)
* Счёт на оплату (по форме 1С)
* Счёт-фактура
* Акт выполненных работ
* Универсальный передаточный документ (УПД), в том числе без печатей

Печатные формы доступны из счетов (раздел «Клиенты») и из заказов продаж.
    """,

    'author': "MK.Lab, RuOdoo",
    'website': "https://ruodoo.ru",

    'license': 'AGPL-3',
    'category': 'Localization',
    'version': '20.0.2026.09.17',

    'depends': ['base', 'sale', 'account', 'sale_stock', 'uom', 'l10n_ru_base', 'l10n_ru_banks', 'docx_report_generation'],

    'external_dependencies': {'python': ['pytils']},

    'data': [
        'views/account_invoice_view.xml',
        'views/res_partner_view.xml',
        'views/res_company_view.xml',
        'views/res_users_view.xml',
        'views/res_partner_bank_view.xml',
        'views/uom.xml',
        'views/tax.xml',
        'views/product.xml',
        'views/l10n_ru_doc_data.xml',
        'report/l10n_ru_doc_report.xml',
        'report/report_order.xml',
        'report/report_invoice.xml',
        'report/report_bill.xml',
        'report/report_act.xml',
        'report/report_upd.xml',
        'report/report_updn.xml',
    ],

    'demo': [
        'demo/l10n_ru_doc_demo.xml',
        'demo/l10n_ru_doc_demo_extra.xml',
    ],
}

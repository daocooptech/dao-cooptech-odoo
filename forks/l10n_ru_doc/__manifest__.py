# -*- coding: utf-8 -*-
{
    'name': "Российская локализация - Документы",

    'summary': "Первичные документы",

    'description': """
Модуль для печати документов в соответствии с законодательством России.
============================================================
Возможности:
    * Товарная накладная (ТОРГ-12)
    * Счет на оплату (по форме 1С)
    * Счет-фактура
    * Акт выполненных работ
    * Универсальный передаточный документ
    
Для печати:    
    Товарная накладная (ТОРГ-12)
        1. Меню Бухгалтерия - Клиенты - Счета (account.move);
        2. Отчет "Товарная накладная (ТОРГ-12)".
    
    Счет на оплату (по форме 1С)
        1. Меню Продажи - Заказ продаж (sale.order));
        2. Отчет "Счет по форме 1С".
    
    Счет-фактура
        1. Меню Бухгалтерия - Клиенты - Счета (account.move);
        2. Отчет "Счет-фактура".
    
    Акт выполненных работ
        1. Меню Бухгалтерия - Клиенты - Счета (account.move);
        2. Отчет "Акт выполненных работ".
    
    Универсальный передаточный документ
        1. Меню Бухгалтерия - Клиенты - Счета (account.move);
        2. В двух вариантах:отчет "Универсальный передаточный документ(УПД)" 
            2.1. Отчет "Универсальный передаточный документ(УПД)";
            2.2. Отчет "УПД без печатей";    
    
    """,

    'author': "CodeUP and MK.Lab",
    'website': "https://www.inf-centre.ru/",

    'license': 'AGPL-3',
    'category': 'Localization',
    'version': '20.0.2025.11.11',

    'depends': ['base', 'sale', 'account', 'sale_stock', 'uom', 'l10n_ru_base', 'docx_report_generation'],

    'external_dependencies': {'python': ['pytils']},

    'data': [
        'views/account_invoice_view.xml',
        'views/res_partner_view.xml',
        'views/res_company_view.xml',
        'views/res_users_view.xml',
        'views/res_bank_view.xml',
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

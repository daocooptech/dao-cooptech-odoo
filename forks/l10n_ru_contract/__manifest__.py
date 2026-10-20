# -*- coding: utf-8 -*-
{
    'name': 'Российская локализация - Договоры',
    'summary': """
       Создание договоров, их видов и печать
    """,

    'description': """
Российская локализация — Договоры
=================================

Учёт договоров с клиентами и поставщиками: разделение по видам договоров,
отслеживание статуса и печать.

Виды договоров:

* Создаются в разделе «Продажи» / «Покупки» → «Договоры» → «Виды договора».
* Для вида задаются журнал и счета дебиторской и кредиторской
  задолженности, а также название.

Договоры:

* Создаются в разделе «Продажи» / «Покупки» → «Договоры».
* В договоре указываются контрагент, тип контрагента, компания
  (от лица которой заключается договор) и вид договора, а также основные
  и дополнительные условия.
* Печать выполняется из записи договора через «Действия» → «Договор».
    """,

    'version': '20.0.2026.09.17',
    'sequence': 0,
    'author': 'MK.Lab, RuOdoo',
    'license': 'LGPL-3',
    'website': 'https://ruodoo.ru',
    'depends': [
        'base',
        'mail',
        'account',
        'sale',
        'l10n_ru_base',
    ],
    "external_dependencies": {
        "python": ["pymorphy3", "python-docx", "docxtpl"],
    },
    'data': [
        'data/data.xml',
        'report/report_contract_simple.xml',
        'views/contract_customer_view.xml',
        "views/contract_header_templates.xml",
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'views/contract_profile_views.xml',
        'views/contract_documents_views.xml',
        'report/report_contract.xml',
        'report/report_contract_invoice.xml',
        'report/report_contract_order.xml',
        'report/report_contract_order1.xml',
        'security/ir.access.csv',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'auto_install': False,
}

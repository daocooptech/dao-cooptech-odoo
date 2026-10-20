# -*- coding: utf-8 -*-
{
    'name': 'УПД из РСБУ-слоя',
    'summary': 'УПД в XML (формат ФНС 5.03, схема 05_03_05) и DOCX из документа реализации РСБУ-слоя',
    'description': """
УПД из РСБУ-слоя для организаций пула
=====================================

Три файла УПД модуля rsbu_fns_reporting (выпуск rudoo 16.10.2026,
dd10b7d) без деклараций, НДФЛ и РСВ: XML по формату ФНС, печать DOCX,
документ реализации из счёта. Весь rsbu_fns_reporting не ставим — он тянет
зарплату и кадры (задача 294, К6).
    """,
    'author': 'MK.Lab, RuOdoo, ДАО КООПТЕХ',
    'website': 'https://ruodoo.ru',
    'category': 'Accounting/Localizations',
    'version': '20.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['rsbu_vat', 'rsbu_reporting_base', 'docx_report', 'coop_invoicing'],
    'data': [
        'data/upd_docx_template.xml',
        'views/rsbu_invoice_upd_views.xml',
    ],
    'post_init_hook': 'post_init_move_upd_requisites',
    'installable': True,
}

# -*- coding: utf-8 -*-
{
    'name': "Российская локализация - УПД в xml-формате",

    'summary': """
        Формирует УПД в формате XML, формат 5.01""",

    'description': """
        Формирует УПД в формате XML.
        
        Для печати:
        1. Меню Бухгалтерия - Клиенты - Счета (account.move);
        2. Кнопка "Печать УПД в xml-формате".
    """,

    'author': "MK.Lab",
    'website': "https://www.inf-centre.ru/",

    'category': 'Uncategorized',
    'version': '19.0.2025.12.11',
    "depends": ["web", "base", "account", "account_payment", "l10n_ru_doc", "l10n_ru_base", "uom"],
    "data": [
        "views/ir_actions_report_view.xml",
        "views/res_partner_view.xml",
        "views/res_company_view.xml",
        "views/res_users_view.xml",
        "views/views_uom_okei.xml",
        "views/view_account_move.xml",
        "reports/report.xml",
        "reports/upd_report.xml",
    ],

    "assets": {
        "web.assets_backend": [
            "l10n_ru_upd_xml/static/src/js/report/action_manager_report.js",
        ],
    },

    "external_dependencies": {
        "python": [ 
            "lxml"
        ]
    },
    "demo": [
        "demo/demo.xml",
    ],
}

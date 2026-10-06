# -*- coding: utf-8 -*-
{
    'name': "Российская локализация - Акт сверки",

    'summary': """
       Добавление отчета акт сверки""",

    'description': """
        Добавление формы акт сверки, находящегося в контактах, с помощью которого можно легко отслеживать дебеторские и кредиторские проводки с клиентами.
        
        Для печати:
        1. Выбираем меню Контакты - конкретного партнера - Действия - "Печать акт сверки";
        2. В визарде выбираем: 
            2.1. Компанию (для которой нужна сверка с выбранным контактом);
            2.2. Период сверки; 
            2.3. Цель (один из режимом: все проведенные проводки или все проводки, включая черновики);
        3. Кнопка "Печать"
        
    """,

    'author': "MK.Lab",
    'website': "https://www.inf-centre.ru/",

    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    "depends": ["account", "portal", "website", 'contacts', "l10n_ru_doc", 'l10n_ru_contract', 'l10n_ru_base'],
    "data": [
        "security/ir.model.access.csv",
        "wizard/general_ledger_wizard_view.xml",
        "report/layouts.xml",
        "report/general_ledger.xml",
        "views/account_account_views.xml",
        "views/report_general_ledger.xml",
        "views/portal_templates.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}

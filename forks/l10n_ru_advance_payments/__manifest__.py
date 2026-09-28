# -*- coding: utf-8 -*-
{
    'name': 'Российская локализация - Авансовые счета',
    'version': '19.0.2025.06.06',
    'description': """Модуль создания новой модели - Авансовые счета. Он добавляет функционал построенный на базовых 
    функциях бухгалтерии.""",

    'author': "MK.Lab",
    'website': "https://www.inf-centre.ru/",

    'depends': ['account',
                'sale',
                'l10n_ru_contract',
                'l10n_ru_doc',
                'l10n_latam_check'
                ],

    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/order_prepaid.xml',
        'views/sale_order.xml',
        'report/order_prepaid.xml',
        'report/report_order_prepaid.xml',
        'report/report_invoice.xml',
        'wizard/account_payment_register_prepaid.xml',
        'views/res_config_settings.xml',
    ],

    "external_dependencies": {
        "python": [
            "pytils"
        ]
    },
    "demo": [
        "demo/demo.xml",
    ],
}

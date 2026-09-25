# -*- coding: utf-8 -*-
{
    'name': 'ДАО КООПТЕХ — документы',
    'summary': 'Акты, договоры и закрывающие с проверяемым отпечатком',
    'description': """
Документы платформы: акты приёма-передачи, договоры, закрывающие.

У каждого документа считается отпечаток — SHA-256 его содержимого.
Человек может загрузить свой экземпляр и увидеть, тот ли это документ:
совпал отпечаток — файл не подменён, разошёлся — перед вами другой файл.

Это работает без всякой цепи блоков. Запись отпечатка в цепь —
следующий шаг поверх готового, и держать из-за неё всю работу
бессмысленно (решение 382).
""",
    'author': 'ДАО КООПТЕХ',
    'website': 'https://daocooptech.ru',
    'category': 'Cooperative',
    'version': '19.0.1.1.0',
    'license': 'LGPL-3',
    'depends': ['coop_base', 'coop_theme', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/coop_document_rules.xml',
        'views/coop_document_more_views.xml',
        'views/coop_document_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'coop_documents/static/src/scss/coop_documents.scss',
            'coop_documents/static/src/js/documents.js',
            'coop_documents/static/src/xml/documents.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
}

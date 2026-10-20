{
    "name": "DOCX Templates",
    "summary": "DOCX-шаблоны",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "category": "Accounting/Localizations",
    "depends": [
        "base",
        "account",
        "sale",
        "l10n_ru_contract",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/docx_template_views.xml",
        "views/docx_report.xml",
        "data/docx_template.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "docx_report/static/src/js/contract_docx_print_menu.js",
            "docx_report/static/src/js/action_manager_report.js",
        ],
    },
    "installable": True,
}

{
    "name": "DOCX Templates",
    "summary": "DOCX-шаблоны",
    "version": "20.0.1.0.0",
    "license": "LGPL-3",
    "category": "Accounting/Localizations",
    # Поверх нашего docx_report_generation (решение владельца 20.10, № 294):
    # тип отчёта docx-docx, поле шаблона, маршруты и обработчик печати в JS
    # живут там, здесь — только каталог шаблонов, переменные и формы.
    "depends": [
        "docx_report_generation",
        "account",
        "sale",
        "l10n_ru_contract",
    ],
    "data": [
        "security/ir.access.csv",
        "views/docx_template_views.xml",
        "data/docx_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "docx_report/static/src/js/contract_docx_print_menu.js",
        ],
    },
    "installable": True,
}

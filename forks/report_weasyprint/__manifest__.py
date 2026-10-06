{
    "name": "Report WeasyPrint",
    "summary": "Рендер пдф документов через WeasyPrint вместо wkhtmltopdf",
    "version": "20.0.1.0.0",
    "category": "Reporting",
    "author": "Mk.lab",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "views/ir_actions_report_views.xml",
    ],
    "external_dependencies": {
        "python": ["weasyprint"],
    },
    "installable": True,
}

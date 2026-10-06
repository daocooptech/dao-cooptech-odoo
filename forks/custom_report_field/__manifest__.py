{
    "name": "Custom report field",
    "summary": """Creates custom computed fields for reports""",
    "description": """
        Adds custom computed fields for reports.
        Adds new tab with custom fields in report form, where custom fields can be
        created. Here is possible write some python code for computing field's value,
        and this field with computed value will be accessible in report template.

        Also adds wizard where custom fields values can be validated before report
        creation.
    """,
    "author": "RYDLAB",
    "website": "https://rydlab.ru",
    "category": "Technical",
    "version": "19.0.2025.11.11",
    "license": "LGPL-3",
    "depends": ["base", "web", "report_monetary_helpers"],
    "data": [
        "views/ir_actions_report_views.xml",
        "wizard/custom_report_field_values_wizard_views.xml",
        'security/ir.access.csv',
    ],
    "assets": {
        "web.assets_backend": [
            "custom_report_field/static/src/js/action_manager_report.js",
        ],
    },
}

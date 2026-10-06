{
    "name": "DaData Connector",
    "summary": """Obtaining data on legal entities from the DaData service""",
    "author": "MK.lab",
    "website": "#",
    "category": "Marketing",
    "version": "19.0.2025.12.03",
    "depends": ["base", "web", "contacts", "account", "l10n_ru_doc"],
    "external_dependencies": {"python": ["dadata==21.10.1"]},
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "wizard/res_partner_auto_data_wizard_views.xml",
        "views/res_config_settings_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "dadata_connector/static/src/views/fields/search/*",
        ],
    },
    "installable": True,
}

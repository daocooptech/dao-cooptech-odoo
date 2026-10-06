from odoo.tests.common import TransactionCase


# Minimal DaData API response fixture for a legal entity (ООО)
DADATA_LEGAL_RESPONSE = [
    {
        "data": {
            "type": "LEGAL",
            "inn": "7707083893",
            "ogrn": "1027700132195",
            "kpp": "773601001",
            "okpo": "00032537",
            "okved": "64.19",
            "opf": {"code": "12300"},
            "name": {
                "short_with_opf": "ПАО Сбербанк",
                "full_with_opf": "Публичное акционерное общество «Сбербанк России»",
            },
            "state": {"status": "ACTIVE"},
            "address": {
                "unrestricted_value": "117997, г Москва, ул Вавилова, д 19",
                "data": {
                    "country_iso_code": "RU",
                    "region_iso_code": "RU-MOW",
                    "city": "Москва",
                    "street_with_type": "ул Вавилова",
                    "house_type_full": "дом",
                    "house": "19",
                    "flat_type_full": None,
                    "flat": None,
                    "postal_code": "117997",
                },
            },
            "documents": {
                "fts_registration": {
                    "series": "77",
                    "number": "004599035",
                    "issue_date": "2002-08-16",
                }
            },
            "management": {
                "name": "ГРЕФ ГЕРМАН ОСКАРОВИЧ",
                "post": "ПРЕЗИДЕНТ, ПРЕДСЕДАТЕЛЬ ПРАВЛЕНИЯ",
            },
        }
    }
]

# Minimal DaData API response fixture for an individual entrepreneur (ИП)
DADATA_INDIVIDUAL_RESPONSE = [
    {
        "data": {
            "type": "INDIVIDUAL",
            "inn": "500100732259",
            "ogrn": "304500116000157",
            "kpp": None,
            "okpo": "0107544",
            "okved": "47.91",
            "opf": {"code": "50102"},
            "fio": {
                "surname": "ИВАНОВ",
                "name": "ИВАН",
                "patronymic": "ИВАНОВИЧ",
            },
            "state": {"status": "ACTIVE"},
            "address": {
                "unrestricted_value": "141001, Московская обл, г Мытищи",
                "data": {
                    "country_iso_code": "RU",
                    "region_iso_code": "RU-MOS",
                    "city": "Мытищи",
                    "street_with_type": None,
                    "house_type_full": None,
                    "house": None,
                    "flat_type_full": None,
                    "flat": None,
                    "postal_code": "141001",
                },
            },
            "documents": {"fts_registration": None},
            "management": None,
        }
    }
]


class DadataConnectorCommon(TransactionCase):
    """Base class for dadata_connector tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({
            "name": "Test Partner",
            "is_company": True,
        })
        cls.env["ir.config_parameter"].sudo().set_param(
            "dadata_connector.dadata_token", "test_token_123"
        )

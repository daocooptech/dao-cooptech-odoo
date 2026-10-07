from odoo import fields, models

# Режимы по заключению бухгалтера 07.10.2026 (НВ15). Код — то, по чему
# выбираются налог строки счёта и функция УПД; название — то, что видит
# человек на карточке организации.
VAT_REGIMES = [
    ('exempt_145', 'Освобождена от НДС (ст. 145 НК)'),
    ('not_payer', 'Не плательщик НДС (АУСН)'),
    ('usn_5', 'УСН, НДС 5 %'),
    ('usn_7', 'УСН, НДС 7 %'),
    ('general_22', 'НДС 22 %'),
]

# Режимы, при которых организация НДС не начисляет: УПД — только
# первичный документ (функция ДОП, статус 2), строки — «без НДС».
NO_VAT_REGIMES = ('exempt_145', 'not_payer')

# Налог строки счёта по режиму: xml-код налога из плана счетов `ru`.
SALE_TAX_BY_REGIME = {
    'exempt_145': 'sale_vat_exempt',
    'not_payer': 'sale_vat_exempt',
    'usn_5': 'sale_vat_5',
    'usn_7': 'sale_vat_7',
    'general_22': 'sale_vat_22',
}

# Налог строки входящего счёта у покупателя — та же ставка, что в УПД
# продавца: покупатель отражает документ таким, каким его получил.
PURCHASE_TAX_BY_REGIME = {
    'exempt_145': 'purchase_vat_exempt',
    'not_payer': 'purchase_vat_exempt',
    'usn_5': 'purchase_vat_5',
    'usn_7': 'purchase_vat_7',
    'general_22': 'purchase_vat_22',
}


class CoopVatRegime(models.Model):
    """Режим НДС организации с даты.

    История, а не флажок: при превышении порога НДС начисляется с первого
    числа следующего месяца (п. 5 ст. 145 НК), и УПД, переотправленный за
    прошлый период, должен выйти с режимом на дату отгрузки, а не на
    сегодня.
    """
    _name = 'coop.vat.regime'
    _description = 'Режим НДС организации'
    _order = 'organization_id, date_from desc'

    organization_id = fields.Many2one(
        'res.partner', string='Организация', required=True, index=True,
        ondelete='cascade')
    date_from = fields.Date(string='С даты', required=True)
    regime = fields.Selection(VAT_REGIMES, string='Режим', required=True)
    note = fields.Char(string='Основание', help='Уведомление, решение, превышение порога.')

    _organization_date_uniq = models.Constraint(
        'unique(organization_id, date_from)',
        'С одной даты у организации может действовать только один режим НДС.')

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rsbu_vat_mode = fields.Selection(
        selection=[
            ('vat_exempt', 'Освобождён от НДС'),
            ('vat_5', 'Спецставка 5%'),
            ('vat_7', 'Спецставка 7%'),
        ],
        string='Режим НДС на УСН', default='vat_exempt')

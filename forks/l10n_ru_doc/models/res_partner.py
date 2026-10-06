from odoo import fields, models
class ResPartner(models.Model):
    _inherit = 'res.partner'

    inn = fields.Char('INN', related='vat')
    kpp = fields.Char('KPP', size=9)
    okpo = fields.Char('OKPO', size=14)
    company_registry = fields.Char('ОГРН/ОГРНИП', copy=False)
    ogrn = fields.Char('ОГРН')
    type = fields.Selection(selection_add=[('director', 'Директор'), ('accountant', 'Бухгалтер')])
    facsimile = fields.Binary("Подпись")
    stamp = fields.Binary("Печать")

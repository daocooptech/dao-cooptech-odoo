from odoo import api, fields, models, exceptions, _

class ContractProfile(models.Model):
    _name = 'contract.profile'

    name = fields.Char(string=_('Вид договора'), required=True)

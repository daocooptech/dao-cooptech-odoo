from odoo import api, fields, models, exceptions, _

class ContractProfile(models.Model):
    _name = 'contract.profile'
    _description = 'contract.profile'

    name = fields.Char(string='Вид договора', required=True)

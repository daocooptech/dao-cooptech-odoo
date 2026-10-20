from odoo import fields, models, _

class ContractDay(models.Model):
    _name = 'contract.day'
    _description = 'contract.day'
    name = fields.Char('День')

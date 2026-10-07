from odoo import api, fields, models, exceptions, _

class ContractDay(models.Model):
    _name = 'contract.day'
    _description = 'contract.day'
    name = fields.Char('День')

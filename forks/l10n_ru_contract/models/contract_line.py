from odoo import api, fields, models, exceptions, tools, _

class ContractLine(models.Model):
    _name = 'contract.line'
    _order = "sequence desc"


    contract_id = fields.Many2one('partner.contract.customer', string='Order Reference', required=True,
                                  ondelete='cascade', index=True, copy=False)
    sequence = fields.Integer('Порядок')
    name = fields.Char('Номер пункта')
    punct = fields.Html('Текст пункта')

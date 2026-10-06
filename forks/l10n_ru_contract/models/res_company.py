from odoo import api, fields, models, exceptions, _

class Company(models.Model):
    _inherit = 'res.company'

    inn = fields.Char(related='partner_id.inn', readonly=False)
    kpp = fields.Char(related='partner_id.kpp', readonly=False)
    okpo = fields.Char(related='partner_id.okpo', readonly=False)
    chief_id = fields.Many2one('res.users', 'Имя директора')
    stamp = fields.Binary("Stamp")
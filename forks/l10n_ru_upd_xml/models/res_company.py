from odoo import fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    inn = fields.Char(related='partner_id.inn', readonly=False, string='ИНН')
    kpp = fields.Char(related='partner_id.kpp', readonly=False, string='КПП')
    okpo = fields.Char(related='partner_id.okpo', readonly=False, string='ОКПО')
    edi = fields.Char(string='ID EDI', readonly=False)
    chief_id = fields.Many2one('res.users', string='Управляющий')

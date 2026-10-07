from odoo import fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    inn = fields.Char(related='partner_id.inn', readonly=False, string='ИНН')
    kpp = fields.Char(related='partner_id.kpp', readonly=False, string='КПП')
    okpo = fields.Char(related='partner_id.okpo', readonly=False, string='ОКПО')
    edi = fields.Char(string='ID EDI', readonly=False)
    # Код оператора ЭДО — первые три знака ID участника (2BM — Контур.Диадок,
    # 2AL — Тензор/СБИС, 2AE — Калуга Астрал …). Подставляется к ID без кода.
    edi_operator = fields.Char(string='Код оператора ЭДО', size=3, default='2BM')
    chief_id = fields.Many2one('res.users', string='Управляющий')

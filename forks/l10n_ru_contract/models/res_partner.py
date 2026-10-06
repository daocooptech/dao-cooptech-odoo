from odoo import api, fields, models, exceptions, _

class Partner(models.Model):
    _inherit = 'res.partner'

    ogrn = fields.Char('ОГРН')
    okpo = fields.Char('ОКПО')
    inn = fields.Char('ИНН')
    kpp = fields.Char('KPP')
    passport = fields.Char('Паспорт')

    contract_count = fields.Integer(string='Договоры', compute='get_count_contract')
    pol = fields.Selection(string="Пол", selection=[('m', 'Муж.'), ('j', 'Жен'), ], required=False)
    type = fields.Selection(selection_add=[('director', 'Директор')])

    def get_count_contract(self):
        contract = self.env['partner.contract.customer']
        for s in self:
            s.contract_count = contract.search_count([('partner_id', '=', s.id)])

    def action_view_contract(self):
        action = self.env.ref('l10n_ru_contract.contract_customer_action').read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        return action
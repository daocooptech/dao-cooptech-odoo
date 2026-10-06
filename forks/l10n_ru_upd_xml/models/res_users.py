from odoo import api, fields, models, _

class ResUsers(models.Model):
    _inherit = 'res.users'

    last_name = fields.Char(string=_('Фамилия'), compute='_compute_update_name')
    first_name = fields.Char(string=_('Имя'), compute='_compute_update_name')
    second_name = fields.Char(string=_('Отчество'), compute='_compute_update_name')

    @api.depends('name')
    def _compute_update_name(self):
        for s in self:
            s.last_name = ''
            s.first_name = ''
            s.second_name = ''
            if s.name:
                s.last_name = s.name
                s.first_name = ''
                s.second_name = ''
                if len(s.name.split(' ')) == 3:
                    s.last_name, s.first_name, s.second_name = s.name.split(' ')
                if len(s.name.split(' ')) == 4:
                    s.last_name, s.first_name, second_name1, second_name2 = s.name.split(' ')
                    s.second_name = second_name1 + ' ' + second_name2
             

from odoo import api, fields, models

class AllowedProfiles(models.Model):
    _name = 'contract.allowed.profiles'
    name = fields.Char(string='Одновременно включены следующие виды договоров:')
    allowed_profiles = fields.Many2many('contract.profile', string='Виды договоров', required=True)

    @api.onchange('allowed_profiles')
    def set_name(self):
        for s in self:
            s.name = ''
            for profile in s.allowed_profiles:
                s.name += profile.name + ' + '
            if s.name:
                if s.name[-2] == '+':
                    s.name = s.name[:-2]
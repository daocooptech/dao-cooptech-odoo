from odoo import api, fields, models, _

class ResPartner(models.Model):
    _inherit = 'res.partner'

    inn = fields.Char('ИНН', size=12)
    kpp = fields.Char('КПП', size=9)
    okpo = fields.Char('ОКПО', size=14)
    edi = fields.Char('ID EDI')
    house = fields.Char('Дом')
    office = fields.Char('Квартира, офис')
    fias_id = fields.Char('Код ФИАС')
    last_name_IP = fields.Char('Фамилия ИП', compute='_compute_get_fio', readonly=False)
    first_name_IP = fields.Char('Имя ИП', compute='_compute_get_fio', readonly=False)
    middle_name_IP = fields.Char('Отчество ИП', compute='_compute_get_fio', readonly=False)

    @api.depends('name')
    def _compute_get_fio(self):
        for s in self:
            if s.name:
                name = s.name
                if name.find('ИП ') != -1:
                    name = name[name.find(' ') + 1:]
                    s.last_name_IP = name[:name.find(' ')]
                    name = name[name.find(' ') + 1:]
                    s.first_name_IP = name[:name.find(' ')]
                    name = name[name.find(' ') + 1:]
                    s.middle_name_IP = name
                else:
                    s.last_name_IP = ""
                    s.first_name_IP = ""
                    s.middle_name_IP = ""
            else:
                s.last_name_IP = ""
                s.first_name_IP = ""
                s.middle_name_IP = ""

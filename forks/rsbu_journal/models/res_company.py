from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rsbu_lock_date = fields.Date(
        string='РСБУ: период закрыт по',
        help='Операции РСБУ-слоя с этой датой и раньше нельзя провести, '
             'вернуть в черновик или сторнировать задним числом. Ставится '
             'при закрытии месяца, снимается при его переоткрытии.')

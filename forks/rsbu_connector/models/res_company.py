from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rsbu_enabled = fields.Boolean(
        string='Учёт в РСБУ-слое',
        help='Проведённые счета и платежи организации получают проводки '
             'РСБУ-слоя. Включается по организации: пул ведёт учёт в слое '
             'не весь сразу.')
    rsbu_start_date = fields.Date(
        string='РСБУ-слой с',
        help='Документы раньше этой даты в слой не попадают '
             '(остатки на эту дату вводятся отдельно).')

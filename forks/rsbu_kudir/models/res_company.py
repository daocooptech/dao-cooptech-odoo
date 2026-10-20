from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rsbu_usn_mode = fields.Selection(
        selection=[
            ('usn_income', 'УСН «Доходы»'),
            ('usn_income_expense', 'УСН «Доходы минус расходы»'),
        ],
        string='Режим УСН', default='usn_income')
    rsbu_usn_rate = fields.Float(
        string='Ставка УСН, %', default=6.0,
        help='Ставка налога при УСН (6% для «Доходы», 15% для «Доходы минус '
             'расходы»; может быть снижена региональным законом).')
    rsbu_usn_reduction_limit = fields.Float(
        string='Лимит уменьшения на взносы, %', default=50.0,
        help='Предел уменьшения налога УСН «Доходы» на страховые взносы и '
             'пособия: 50% для организаций и ИП с работниками, 100% для ИП '
             'без работников.')
    rsbu_accounting_start = fields.Date(
        string='Дата начала учёта РСБУ',
        help='Дата, с которой ведётся учёт в РСБУ-слое. Месяц этой даты — '
             'первый доступный для закрытия периода; более ранние месяцы '
             'закрывать не требуется и нельзя.')

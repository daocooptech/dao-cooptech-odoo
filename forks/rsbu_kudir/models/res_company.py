from odoo import fields, models

# Расчётная доля НДС в сумме «в том числе» по режиму НДС.
VAT_FRACTION = {'vat_5': 5.0 / 105.0, 'vat_7': 7.0 / 107.0,
                'vat_22': 22.0 / 122.0}


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
    # Режим НДС объявлен здесь, а не в rsbu_vat: КУДиР читает его сама,
    # а rsbu_vat стоит выше по цепочке.
    rsbu_vat_mode = fields.Selection(
        selection=[
            ('vat_exempt', 'Освобождён от НДС'),
            ('vat_5', 'Спецставка 5%'),
            ('vat_7', 'Спецставка 7%'),
            ('vat_22', 'НДС 22%'),
        ],
        string='Режим НДС', default='vat_exempt',
        help='Для компании без истории режимов. Режим организации пула '
             'берётся на дату документа (_rsbu_vat_mode_at).')
    # Одна дата начала учёта в слое — rsbu_start_date из rsbu_connector.
    rsbu_accounting_start = fields.Date(
        related='rsbu_start_date', readonly=False,
        string='Дата начала учёта РСБУ',
        help='Дата, с которой ведётся учёт в РСБУ-слое. Месяц этой даты — '
             'первый доступный для закрытия периода; более ранние месяцы '
             'закрывать не требуется и нельзя.')

    def _rsbu_vat_mode_at(self, date):
        """Режим НДС компании на дату: vat_exempt / vat_5 / vat_7 / vat_22.

        У выпуска — флажок на компании «сейчас». Пул переопределяет метод:
        режим организации ведётся историей с датой (coop.vat.regime), и
        документ прошлого периода должен считаться по режиму своей даты.
        """
        self.ensure_one()
        return self.rsbu_vat_mode or 'vat_exempt'

    def _rsbu_vat_fraction_at(self, date):
        """Доля НДС в сумме «в том числе» по режиму на дату (0 — без НДС)."""
        self.ensure_one()
        return VAT_FRACTION.get(self._rsbu_vat_mode_at(date), 0.0)

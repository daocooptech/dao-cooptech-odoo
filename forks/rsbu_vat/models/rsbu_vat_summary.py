from odoo import api, fields, models


class RsbuVatSummary(models.Model):
    """Регистр промежуточных итогов НДС за квартал."""
    _name = 'rsbu.vat.summary'
    _description = 'РСБУ — Итоги НДС за период'
    _order = 'period_key desc'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    period_key = fields.Char(string='Квартал', required=True, index=True)
    tax_base = fields.Monetary(string='Налоговая база',
                               currency_field='currency_id')
    vat_charged = fields.Monetary(string='НДС начислен',
                                  currency_field='currency_id')
    vat_deducted = fields.Monetary(string='Вычеты',
                                   currency_field='currency_id')
    vat_payable = fields.Monetary(string='НДС к уплате',
                                  currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Валюта',
                                  compute='_compute_currency_id', store=True)

    @api.depends('company_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id


    @api.model
    def recompute_period(self, date_from, date_to, company):
        """Пересчитать итоги НДС по кварталам периода из книг.

        Налоговая база начисления (tax_base) восстанавливается из суммы
        начисленного НДС по расчётной ставке режима компании (5/105 или
        7/107): база = НДС × (1/доля − 1). Для единой спецставки УСН это
        точно; при смешанных ставках потребуется база из строк книги
        (base_amount) — TODO.
        """
        BookLine = self.env['rsbu.vat.book.line']
        book_lines = BookLine.search([
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ])
        by_period = {}
        for bl in book_lines:
            data = by_period.setdefault(
                bl.period_key,
                {'charged': 0.0, 'deducted': 0.0, 'base': 0.0,
                 'date': bl.date})
            data['date'] = max(data['date'], bl.date)
            if bl.book == 'sales':
                data['charged'] += bl.vat_amount
                # База из строки, если задана; иначе восстановим ниже по ставке.
                data['base'] += bl.base_amount
            else:
                data['deducted'] += bl.vat_amount

        result = self.browse()
        for period_key, data in by_period.items():
            tax_base = data['base']
            # Режим НДС — на конец квартала (у выпуска — «сейчас»).
            fraction = company._rsbu_vat_fraction_at(data['date'])
            # Если база в строках не заполнена — восстановить из НДС по ставке.
            if not tax_base and fraction and data['charged']:
                # база = НДС / доля − НДС = НДС × (1/доля − 1)
                tax_base = round(
                    data['charged'] * (1.0 / fraction - 1.0), 2)
            existing = self.search([
                ('company_id', '=', company.id),
                ('period_key', '=', period_key)], limit=1)
            vals = {
                'company_id': company.id,
                'period_key': period_key,
                'tax_base': tax_base,
                'vat_charged': data['charged'],
                'vat_deducted': data['deducted'],
                'vat_payable': data['charged'] - data['deducted'],
            }
            if existing:
                existing.write(vals)
                result |= existing
            else:
                result |= self.create(vals)
        return result

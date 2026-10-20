from odoo import api, fields, models

# Код счёта начисленного НДС по умолчанию (кодировка 94н). Фактический счёт
# определяется по роли `vat_output` шаблонов маппинга (может быть 68.02 в
# кодировке 1С), а эта константа — фолбэк, если роль нигде не задана.
VAT_OUTPUT_CODE = '68.НДС'
# Код счёта единого налогового счёта (ЕНС). Перенос сальдо НДС на ЕНС
# (Дт 68.02 − Кт 68.90) — регламентная операция уплаты налога, а не
# начисление/вычет НДС, поэтому такие проводки в книги НДС не попадают.
ENS_ACCOUNT_CODE = '68.90'


class RsbuVatBookLine(models.Model):
    """Запись книги продаж / покупок (собирается из проводок НДС журнала)."""
    _name = 'rsbu.vat.book.line'
    _description = 'РСБУ — Запись книги НДС'
    _order = 'date, id'
    _check_company_auto = True

    book = fields.Selection(
        selection=[('sales', 'Книга продаж'),
                   ('purchases', 'Книга покупок')],
        string='Книга', required=True, index=True)
    date = fields.Date(string='Дата', required=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    move_id = fields.Many2one('rsbu.move', string='Операция',
                              ondelete='cascade')
    move_line_id = fields.Many2one('rsbu.move.line', string='Строка журнала',
                                   ondelete='cascade')
    invoice_id = fields.Many2one('rsbu.invoice', string='Счёт-фактура')
    partner_id = fields.Many2one('res.partner', string='Контрагент')
    base_amount = fields.Monetary(string='База', currency_field='currency_id')
    vat_amount = fields.Monetary(string='Сумма НДС',
                                 currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Валюта',
                                  compute='_compute_currency_id', store=True)
    period_key = fields.Char(string='Квартал', compute='_compute_period_key',
                             store=True, index=True)

    @api.depends('company_id')
    def _compute_currency_id(self):
        for line in self:
            line.currency_id = line.company_id.currency_id

    @api.depends('date')
    def _compute_period_key(self):
        for line in self:
            if line.date:
                quarter = (line.date.month - 1) // 3 + 1
                line.period_key = '%s-Q%s' % (line.date.year, quarter)
            else:
                line.period_key = False

    @api.model
    def _vat_output_accounts(self, company):
        """Счета начисленного НДС для компании (по роли vat_output).

        Определяем счёт(а) НДС по роли `vat_output` в шаблонах маппинга —
        это работает независимо от кодировки (68.НДС в академическом плане
        либо 68.02 в кодировке 1С). Фолбэк — счёт с кодом VAT_OUTPUT_CODE.
        """
        Role = self.env['rsbu.operation.template.role'].sudo()
        roles = Role.search([
            ('role', '=', 'vat_output'),
            ('company_id', 'in', (False, company.id)),
        ])
        accounts = roles.mapped('account_id')
        if not accounts:
            accounts = self.env['rsbu.account'].sudo().search([
                ('code', '=', VAT_OUTPUT_CODE),
                ('company_id', '=', company.id)], limit=1)
        return accounts

    @api.model
    def _ens_accounts(self, company):
        """Счёт(а) единого налогового счёта (ЕНС) для компании (код 68.90)."""
        return self.env['rsbu.account'].sudo().search([
            ('code', '=', ENS_ACCOUNT_CODE),
            ('company_id', '=', company.id)])

    @api.model
    def _is_ens_transfer(self, move, vat_accounts, ens_accounts):
        """Проводка — перенос НДС на ЕНС (не операция начисления/вычета).

        Признак: в проводке одновременно есть строка счёта НДС (vat_output)
        и строка счёта ЕНС (68.90). Такой перенос сальдо расчётов по НДС на
        единый налоговый счёт не является ни начислением (книга продаж), ни
        вычетом (книга покупок) — в книги НДС не попадает.
        """
        if not ens_accounts:
            return False
        accounts = move.line_ids.mapped('account_id')
        return bool(accounts & vat_accounts) and bool(accounts & ens_accounts)

    @api.model
    def _is_vat_account(self, account, vat_accounts=None):
        if vat_accounts is not None:
            return account in vat_accounts
        # Обратная совместимость (одиночный вызов): сверка по коду.
        return account.code == VAT_OUTPUT_CODE

    @api.model
    def recompute_period(self, date_from, date_to, company):
        """Пересобрать книги продаж/покупок за период из проводок журнала.

        Книга продаж — начисление НДС (Кт счёта vat_output);
        книга покупок — вычет НДС (Дт счёта vat_output).
        Счёт НДС определяется по роли (68.НДС или 68.02). Идемпотентно.

        TODO(perf): при больших объёмах вынести в cron. Сейчас не делаем.
        """
        self.search([
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]).unlink()

        vat_accounts = self._vat_output_accounts(company)
        ens_accounts = self._ens_accounts(company)
        lines = self.env['rsbu.move.line'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ])
        vals_list = []
        for line in lines:
            if not self._is_vat_account(line.account_id, vat_accounts):
                continue
            # Перенос сальдо НДС на ЕНС (Дт 68.02 − Кт 68.90) — регламентная
            # уплата налога, не начисление/вычет НДС. В книги не включаем.
            if self._is_ens_transfer(line.move_id, vat_accounts, ens_accounts):
                continue
            if line.credit:  # начисление -> книга продаж
                vals_list.append(self._line_vals(line, 'sales',
                                                 line.credit))
            elif line.debit:  # вычет -> книга покупок
                vals_list.append(self._line_vals(line, 'purchases',
                                                 line.debit))
        if vals_list:
            return self.create(vals_list)
        return self.browse()

    @api.model
    def _line_vals(self, line, book, vat_amount):
        return {
            'book': book,
            'date': line.date,
            'company_id': line.company_id.id,
            'move_id': line.move_id.id,
            'move_line_id': line.id,
            'partner_id': line.partner_id.id or False,
            'vat_amount': vat_amount,
        }

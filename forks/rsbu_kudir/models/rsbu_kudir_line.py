from odoo import api, fields, models

# Коды денежных счетов (по плану 94н): касса и расчётные счета.
MONEY_ACCOUNT_CODES = ('50', '51', '52', '55', '57')
# Код счёта расчётов по страховым взносам (для раздела IV).
INSURANCE_ACCOUNT_CODE = '69'


class RsbuKudirLine(models.Model):
    """Запись КУДиР (кассовый слой поверх журнала)."""
    _name = 'rsbu.kudir.line'
    _description = 'РСБУ — Запись КУДиР'
    _order = 'date, id'
    _check_company_auto = True

    date = fields.Date(string='Дата', required=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    section = fields.Selection(
        selection=[
            ('section_1', 'Раздел I. Доходы и расходы'),
            ('section_4', 'Раздел IV. Страховые взносы'),
        ],
        string='Раздел', required=True, index=True)
    move_id = fields.Many2one('rsbu.move', string='Операция-источник',
                              ondelete='cascade')
    move_line_id = fields.Many2one('rsbu.move.line', string='Строка журнала',
                                   ondelete='cascade')
    document_ref = fields.Char(string='Первичный документ')
    narration = fields.Char(string='Содержание операции')
    income_amount = fields.Monetary(string='Доходы',
                                    currency_field='currency_id')
    expense_amount = fields.Monetary(string='Расходы',
                                     currency_field='currency_id')
    is_refund = fields.Boolean(string='Возврат')
    currency_id = fields.Many2one('res.currency', string='Валюта',
                                  compute='_compute_currency_id', store=True)
    period_key = fields.Char(string='Период', compute='_compute_period_key',
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

    # ------------------------------------------------------------------
    # Пересчёт
    # ------------------------------------------------------------------
    @api.model
    def _is_money_account(self, account):
        code = (account.code or '').split('.')[0]
        return code in MONEY_ACCOUNT_CODES

    @api.model
    def _is_insurance_account(self, account):
        code = (account.code or '').split('.')[0]
        return code == INSURANCE_ACCOUNT_CODE

    @api.model
    def recompute_period(self, date_from, date_to, company):
        """Пересобрать записи КУДиР за период из проведённых проводок.

        Идемпотентно: сначала удаляет существующие записи периода,
        затем создаёт заново.

        TODO(perf): при больших объёмах вынести в cron пакетного
        пересчёта. Сейчас крон не реализуется (см. спецификацию Э5 R6.4).
        """
        # 1) Удалить существующие записи за период.
        self.search([
            ('company_id', '=', company.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]).unlink()

        usn_mode = company.rsbu_usn_mode
        # Отбираем проводки, участвующие в УСН (доход/расход/возврат), а также
        # проводки с корректировкой дохода при отгрузке (переходящие сделки —
        # см. kudir_income_adjust), даже если сама проводка не признаётся
        # доходом по кассе (usn_recognition='none').
        moves = self.env['rsbu.move'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            '|',
                '&', ('usn_recognition', 'not in', ('none', False)),
                     (1, '=', 1),
                ('kudir_income_adjust', '!=', 0.0),
        ])
        created = self.browse()
        for move in moves:
            created |= self._build_lines_for_move(move, usn_mode)
        return created

    @api.model
    def _build_lines_for_move(self, move, usn_mode):
        vals_list = []
        recognition = move.usn_recognition
        # Корректировка дохода при отгрузке в счёт входящего аванса
        # (переходящая сделка УСН→УСН+НДС): отдельная строка раздела I на
        # сумму kudir_income_adjust (обычно отрицательная), не связанная с
        # движением денег. Первичный документ/содержание — от проводки
        # реализации (документ отгрузки).
        adjust = getattr(move, 'kudir_income_adjust', 0.0) or 0.0
        if adjust:
            vals_list.append(self._line_vals(
                move, move.line_ids[:1], 'section_1',
                income_amount=round(adjust, 2)))
        for line in move.line_ids:
            account = line.account_id
            # Раздел IV: уплата страховых взносов (дебет счёта 69).
            if self._is_insurance_account(account) and line.debit:
                vals_list.append(self._line_vals(
                    move, line, 'section_4',
                    expense_amount=line.debit))
                continue
            # Раздел I: движение денег.
            if not self._is_money_account(account):
                continue
            amount = line.debit or line.credit
            if recognition == 'income' and line.debit:
                # Доход УСН = поступление минус предъявленный НДС (на УСН+НДС
                # НДС в доход не включается). НДС берётся из документа-
                # источника (move.kudir_income_vat), для необлагаемых = 0.
                vat = getattr(move, 'kudir_income_vat', 0.0) or 0.0
                income = round(amount - vat, 2)
                vals_list.append(self._line_vals(
                    move, line, 'section_1', income_amount=income))
            elif recognition == 'refund_customer' and line.credit:
                vals_list.append(self._line_vals(
                    move, line, 'section_1', income_amount=-amount,
                    is_refund=True))
            elif recognition == 'expense' and line.credit \
                    and usn_mode == 'usn_income_expense':
                vals_list.append(self._line_vals(
                    move, line, 'section_1', expense_amount=amount))
            elif recognition == 'refund_supplier' and line.debit \
                    and usn_mode == 'usn_income_expense':
                vals_list.append(self._line_vals(
                    move, line, 'section_1', expense_amount=-amount,
                    is_refund=True))
        if not vals_list:
            return self.browse()
        return self.create(vals_list)

    @api.model
    def _line_vals(self, move, line, section, income_amount=0.0,
                   expense_amount=0.0, is_refund=False):
        return {
            'date': move.date,
            'company_id': move.company_id.id,
            'section': section,
            'move_id': move.id,
            'move_line_id': line.id,
            'document_ref': move.name,
            'narration': move.ref or line.name or '',
            'income_amount': income_amount,
            'expense_amount': expense_amount,
            'is_refund': is_refund,
        }

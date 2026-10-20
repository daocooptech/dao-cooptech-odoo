# -*- coding: utf-8 -*-
"""Акт сверки взаиморасчётов по РСБУ-слою.

Собирает сальдо и обороты по контрагенту за период из журнала РСБУ
(rsbu.move.line) по счетам расчётов (активно-пассивные счета с субконто
«Контрагент» — 60/62/76). Строки акта — хозяйственные операции по этому
контрагенту с суммами по дебету/кредиту (с позиции нашей организации).

Выгрузка: печатная форма DOCX (docx_report) и электронный XML обмена
(приказ ФНС 405, КНД 1110332) — в отдельных файлах-примесях.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Счета бухучёта, участвующие в акте сверки с контрагентом (по коду):
#   60 — расчёты с поставщиками и подрядчиками;
#   62 — расчёты с покупателями и заказчиками;
#   76 — расчёты с разными дебиторами и кредиторами;
#   66/67 — кредиты и займы (реже); 58 — предоставленные займы.
# Берутся сам счёт и его расчётные субсчета, КРОМЕ технических субсчетов
# авансового НДС/спецсчетов с суффиксом «.АВ» (напр. 76.АВ «НДС по авансам»,
# 62.АВ) — они к задолженности контрагента не относятся.
RECONCILE_ACCOUNT_PREFIXES = ('60', '62', '76', '66', '67', '58')
RECONCILE_EXCLUDE_SUFFIX = '.АВ'


class RuodooRsbuAct(models.Model):
    _name = 'ruodoo.rsbu.act'
    _description = 'РСБУ — Акт сверки взаиморасчётов'
    _order = 'date_to desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Номер акта', default='/', copy=False,
                       index=True)
    # По умолчанию — единственная организация со слоем среди выбранных;
    # компания по умолчанию в пуле — платформа (все компании разрешены).
    company_id = fields.Many2one(
        'res.company', string='Организация', required=True, index=True,
        default=lambda self: self._default_rsbu_company())
    partner_id = fields.Many2one(
        'res.partner', string='Контрагент', required=True, index=True)
    date_from = fields.Date(
        string='Период с', required=True,
        default=lambda self: fields.Date.today().replace(month=1, day=1))
    date_to = fields.Date(
        string='Период по', required=True,
        default=fields.Date.context_today)
    account_ids = fields.Many2many(
        'rsbu.account', string='Счета расчётов',
        domain="[('subconto_partner', '=', True), ('is_group', '=', False), "
               "('company_id', '=', company_id)]",
        help='Счета расчётов для сверки (активно-пассивные с субконто '
             '«Контрагент»: 60/62/76). Пусто — берутся все такие счета.')
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id')
    state = fields.Selection(
        selection=[('draft', 'Черновик'), ('computed', 'Рассчитан')],
        default='draft', string='Состояние', copy=False)
    line_ids = fields.One2many(
        'ruodoo.rsbu.act.line', 'act_id', string='Операции')

    # Сальдо и обороты (с позиции нашей организации по счетам расчётов).
    opening_debit = fields.Monetary(
        string='Сальдо нач. (дебет)', currency_field='currency_id',
        compute='_compute_totals', store=True)
    opening_credit = fields.Monetary(
        string='Сальдо нач. (кредит)', currency_field='currency_id',
        compute='_compute_totals', store=True)
    turnover_debit = fields.Monetary(
        string='Оборот по дебету', currency_field='currency_id',
        compute='_compute_totals', store=True)
    turnover_credit = fields.Monetary(
        string='Оборот по кредиту', currency_field='currency_id',
        compute='_compute_totals', store=True)
    closing_debit = fields.Monetary(
        string='Сальдо кон. (дебет)', currency_field='currency_id',
        compute='_compute_totals', store=True)
    closing_credit = fields.Monetary(
        string='Сальдо кон. (кредит)', currency_field='currency_id',
        compute='_compute_totals', store=True)

    @api.model
    def _default_rsbu_company(self):
        companies = self.env.companies.filtered('rsbu_enabled')
        return companies if len(companies) == 1 else self.env['res.company']

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                # У выпуска последовательности нет — номер «АКТ-дата»
                # повторялся. Нумерация своя у каждой организации.
                company = self.env['res.company'].browse(
                    vals.get('company_id') or self._default_rsbu_company().id
                    or self.env.company.id)
                vals['name'] = self.env['ir.sequence']._rsbu_next_for_company(
                    'ruodoo_rsbu_act.seq_ruodoo_rsbu_act', company,
                    vals.get('date_to'))
        return super().create(vals_list)

    @api.depends('line_ids', 'line_ids.debit', 'line_ids.credit',
                 'opening_debit', 'opening_credit')
    def _compute_totals(self):
        for act in self:
            t_deb = sum(act.line_ids.mapped('debit'))
            t_cre = sum(act.line_ids.mapped('credit'))
            act.turnover_debit = t_deb
            act.turnover_credit = t_cre
            # Конечное сальдо = начальное + обороты (развёрнуто по знаку).
            raw = ((act.opening_debit - act.opening_credit)
                   + (t_deb - t_cre))
            act.closing_debit = raw if raw >= 0 else 0.0
            act.closing_credit = -raw if raw < 0 else 0.0

    # ------------------------------------------------------------------
    def _settlement_accounts(self):
        """Счета расчётов для сверки.

        Если счета заданы вручную (account_ids) — используются они. Иначе
        отбираются счета расчётов с контрагентом по коду (60/62/76/66/67/58
        и их расчётные субсчета), исключая технические субсчета авансового
        НДС/спецсчета с суффиксом «.АВ» — они не отражают задолженность
        и засоряют акт.
        """
        self.ensure_one()
        if self.account_ids:
            return self.account_ids
        accounts = self.env['rsbu.account'].search([
            ('company_id', '=', self.company_id.id),
            ('subconto_partner', '=', True),
            ('is_group', '=', False),
        ])
        return accounts.filtered(lambda a: self._is_reconcile_account(a.code))

    @staticmethod
    def _is_reconcile_account(code):
        """Код счёта относится к сверяемым расчётам (не технический аванс)."""
        code = (code or '').strip()
        if RECONCILE_EXCLUDE_SUFFIX in code:
            return False
        root = code.split('.')[0]
        return root in RECONCILE_ACCOUNT_PREFIXES

    def _move_line_domain(self, date_from, date_to):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('account_id', 'in', self._settlement_accounts().ids),
            ('state', '=', 'posted'),
        ]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        return domain

    def _opening_balance(self):
        """Сальдо на начало периода (развёрнуто дебет/кредит)."""
        self.ensure_one()
        Line = self.env['rsbu.move.line']
        lines = Line.search(self._move_line_domain(None, False) + [
            ('date', '<', self.date_from)])
        raw = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))
        raw = round(raw, 2)
        return (raw, 0.0) if raw >= 0 else (0.0, -raw)

    # ------------------------------------------------------------------
    def action_compute(self):
        """Собрать операции и сальдо по контрагенту за период."""
        Line = self.env['ruodoo.rsbu.act.line']
        MoveLine = self.env['rsbu.move.line']
        for act in self:
            act.line_ids.unlink()
            od, oc = act._opening_balance()
            act.opening_debit = od
            act.opening_credit = oc
            ml = MoveLine.search(
                act._move_line_domain(act.date_from, act.date_to),
                order='date, move_id, id')
            vals = []
            for line in ml:
                move = line.move_id
                vals.append({
                    'act_id': act.id,
                    'date': line.date,
                    'name': line.name or move.ref or move.name,
                    'move_id': move.id,
                    'doc_name': move.ref or 'Операция',
                    'doc_number': move.name,
                    'doc_date': move.date,
                    'contract_id': line.contract_id.id,
                    'debit': line.debit,
                    'credit': line.credit,
                })
            if vals:
                Line.create(vals)
            act.state = 'computed'
        # Если по одному акту ничего не собралось — явно предупредить
        # (чаще всего выбран не тот контрагент/период или нет проводок на
        # счетах расчётов), чтобы пустой акт не выглядел молчаливой ошибкой.
        if len(self) == 1 and not self.line_ids and not (
                self.opening_debit or self.opening_credit):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Акт сверки пуст'),
                    'message': _(
                        'За период %(df)s — %(dt)s по контрагенту «%(p)s» '
                        'не найдено проводок на счетах расчётов (60/62/76). '
                        'Проверьте выбранного контрагента, период и наличие '
                        'проведённых операций.',
                        df=self.date_from, dt=self.date_to,
                        p=self.partner_id.name),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        return True

    def _check_requisites(self):
        self.ensure_one()
        errors = []
        company_partner = self.company_id.partner_id
        if not company_partner._rsbu_inn():
            errors.append('ИНН организации')
        if not self.partner_id._rsbu_inn():
            errors.append('ИНН контрагента')
        if not self.line_ids and not (self.opening_debit or
                                      self.opening_credit):
            errors.append('нет операций и сальдо за период')
        if errors:
            raise UserError(
                'Не удалось сформировать акт сверки: %s.'
                % ', '.join(errors))


class RuodooRsbuActLine(models.Model):
    _name = 'ruodoo.rsbu.act.line'
    _description = 'РСБУ — Операция акта сверки'
    _order = 'act_id, date, id'

    act_id = fields.Many2one(
        'ruodoo.rsbu.act', string='Акт', required=True,
        ondelete='cascade', index=True)
    currency_id = fields.Many2one(
        'res.currency', related='act_id.currency_id')
    date = fields.Date(string='Дата операции')
    name = fields.Char(string='Содержание операции')
    move_id = fields.Many2one('rsbu.move', string='Проводка РСБУ')
    doc_name = fields.Char(string='Документ')
    doc_number = fields.Char(string='Номер документа')
    doc_date = fields.Date(string='Дата документа')
    contract_id = fields.Many2one(
        'partner.contract.customer', string='Договор')
    debit = fields.Monetary(string='Дебет', currency_field='currency_id')
    credit = fields.Monetary(string='Кредит', currency_field='currency_id')

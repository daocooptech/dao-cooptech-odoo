from odoo import api, fields, models


class RsbuInvoice(models.Model):
    """Счёт-фактура РСБУ — источник расчёта НДС.

    Типы: авансовый (при получении аванса), отгрузочный (при УПД),
    корректировочный (возврат / изменение стоимости).

    Авансовый СФ при подтверждении порождает РСБУ-проводку начисления
    авансового НДС (Дт 76.АВ — Кт 68.НДС) через rsbu.posting.mixin, как
    отдельный документ (аналог «Счёта-фактуры выданного» на аванс в 1С).
    """
    _name = 'rsbu.invoice'
    _description = 'РСБУ — Счёт-фактура'
    _order = 'date desc, name desc, id desc'
    _inherit = ['rsbu.posting.mixin']
    _check_company_auto = True

    name = fields.Char(string='Номер СФ', default='/', copy=False,
                       index=True)
    date = fields.Date(string='Дата СФ', required=True, index=True,
                       default=fields.Date.context_today)
    invoice_type = fields.Selection(
        selection=[
            ('advance', 'Авансовый'),
            ('shipment', 'Отгрузочный (УПД)'),
            ('correction', 'Корректировочный'),
        ],
        string='Тип СФ', required=True, default='advance')
    partner_id = fields.Many2one('res.partner', string='Контрагент',
                                 required=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', string='Валюта', compute='_compute_currency_id',
        store=True)

    # Связь с источником (rsbu_move_id приходит из rsbu.posting.mixin).
    source_model = fields.Char(string='Модель источника', copy=False)
    source_res_id = fields.Integer(string='ID источника', copy=False)
    # Проводка-аванс (документ-основание) — для дроблёного вычета НДС.
    origin_move_id = fields.Many2one(
        'rsbu.move', string='Документ-основание (аванс)', copy=False,
        help='Проводка получения аванса, по которому начислен авансовый НДС.')

    vat_rate = fields.Selection(
        selection=[('vat_exempt', 'Без НДС'), ('vat_5', '5%'),
                   ('vat_7', '7%'), ('vat_22', '22%'), ('vat_20', '20%'),
                   ('vat_10', '10%')],
        string='Ставка НДС', default='vat_5')
    base_amount = fields.Monetary(string='Налоговая база',
                                  currency_field='currency_id')
    vat_amount = fields.Monetary(string='Сумма НДС',
                                 currency_field='currency_id')
    state = fields.Selection(
        selection=[('draft', 'Черновик'), ('confirmed', 'Подтверждён'),
                   ('cancelled', 'Отменён')],
        string='Состояние', default='draft', copy=False)

    # Связь с документом реализации (у отгрузочного СФ). У авансового и
    # корректировочного — NULL. Передаточная часть УПД (upd_*) перенесена на
    # rsbu.realization.
    realization_id = fields.Many2one(
        'rsbu.realization', string='Документ реализации',
        copy=False, ondelete='set null')
    # Исходный СФ для корректировочного СФ (КСФ) — схема-задел, без поведения.
    origin_invoice_id = fields.Many2one(
        'rsbu.invoice', string='Исходный счёт-фактура (для КСФ)',
        copy=False, ondelete='set null')

    @api.depends('company_id')
    def _compute_currency_id(self):
        for inv in self:
            inv.currency_id = inv.company_id.currency_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                company = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = self.env['ir.sequence']._rsbu_next_for_company(
                    'rsbu_vat.seq_rsbu_invoice', company, vals.get('date'))
        return super().create(vals_list)

    # ------------------------------------------------------------------

    def _role_account(self, role):
        """Счёт РСБУ по роли маппинга (vat_output/vat_advance) для компании."""
        self.ensure_one()
        return self._role_account_for_company(role, self.company_id)

    @api.model
    def _role_account_for_company(self, role, company):
        """Счёт РСБУ по роли маппинга для указанной компании (без записи)."""
        Role = self.env['rsbu.operation.template.role'].sudo()
        rec = Role.search([
            ('role', '=', role),
            ('company_id', '=', company.id),
        ], limit=1)
        return rec.account_id

    # ------------------------------------------------------------------
    # Точки rsbu.posting.mixin
    # ------------------------------------------------------------------
    def _rsbu_is_applicable(self):
        """Проводку порождает только авансовый СФ с НДС и заданными счетами."""
        self.ensure_one()
        if self.invoice_type != 'advance':
            return False
        if not self._role_account('vat_advance') \
                or not self._role_account('vat_output'):
            return False
        has_vat = bool(self.vat_amount) or bool(
            self.company_id._rsbu_vat_fraction_at(self._rsbu_move_date()))
        return has_vat

    def _rsbu_move_date(self):
        self.ensure_one()
        return self.date or fields.Date.context_today(self)

    def _rsbu_build_lines(self):
        """Начисление авансового НДС: Дт 76.АВ — Кт 68.НДС.

        Сумма — vat_amount, если задан, иначе base_amount×доля режима НДС.
        origin строки 76.АВ = проводка-аванс (origin_move_id) для дроблёного
        вычета в регламенте книги покупок.
        """
        self.ensure_one()
        vat_advance = self._role_account('vat_advance')
        vat_output = self._role_account('vat_output')
        if not vat_advance or not vat_output:
            return []
        vat = self.vat_amount
        if not vat:
            fraction = self.company_id._rsbu_vat_fraction_at(
                self._rsbu_move_date())
            vat = round((self.base_amount or 0.0) * fraction, 2)
        if vat <= 0:
            return []
        dt = {'account_id': vat_advance.id, 'debit': vat,
              'name': 'НДС с аванса'}
        if self.partner_id:
            dt['partner_id'] = self.partner_id.id
        if self.origin_move_id:
            dt['origin_move_id'] = self.origin_move_id.id
        kt = {'account_id': vat_output.id, 'credit': vat,
              'name': 'НДС с аванса начислен'}
        return [dt, kt]

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        for inv in self:
            inv._rsbu_generate()

    def action_cancel(self):
        self._rsbu_remove()
        self.write({'state': 'cancelled'})

    # ------------------------------------------------------------------
    # Связь с инвойсом-источником (для товарных позиций УПД, Вариант B)
    # ------------------------------------------------------------------
    def _source_invoice(self):
        """Вернуть документ-источник (account.move), если СФ создан из него.

        Товарные позиции УПД (наименование/кол-во/ОКЕИ/ГТИН) берутся из
        инвойса Odoo, а финансовые показатели СФ — из РСБУ-слоя (Вариант B).
        """
        self.ensure_one()
        if self.source_model == 'account.move' and self.source_res_id:
            move = self.env['account.move'].browse(self.source_res_id)
            return move if move.exists() else self.env['account.move']
        return self.env['account.move']

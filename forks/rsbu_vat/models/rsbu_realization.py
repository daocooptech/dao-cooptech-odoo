from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Процент ставки налога строки → значение vat_rate счёта-фактуры.
_PCT_TO_VAT_RATE = [
    (20.0, 'vat_20'),
    (10.0, 'vat_10'),
    (7.0, 'vat_7'),
    (5.0, 'vat_5'),
]


class RsbuRealization(models.Model):
    """РСБУ — Документ реализации.

    Первичный документ отгрузки (эволюция отгрузочного счёта-фактуры).
    Создаётся для ЛЮБОЙ отгрузки — облагаемой НДС и «Без НДС». Несёт
    передаточную часть УПД (upd_*) и является источником печати и XML УПД.
    При наличии НДС порождает подчинённый отгрузочный счёт-фактуру
    (rsbu.invoice, invoice_id).
    """
    _name = 'rsbu.realization'
    _description = 'РСБУ — Документ реализации'
    _order = 'date desc, name desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Номер документа реализации', default='/',
                       copy=False, index=True)
    date = fields.Date(string='Дата реализации', required=True, index=True,
                       default=fields.Date.context_today)
    partner_id = fields.Many2one('res.partner', string='Контрагент',
                                 required=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', string='Валюта', compute='_compute_currency_id',
        store=True)

    # Связь с источником — инвойс Odoo (как у отгрузочного СФ).
    source_model = fields.Char(string='Модель источника', copy=False)
    source_res_id = fields.Integer(string='ID источника', copy=False)

    state = fields.Selection(
        selection=[('draft', 'Черновик'), ('confirmed', 'Подтверждён'),
                   ('cancelled', 'Отменён')],
        string='Состояние', default='draft', copy=False)

    # --- Передаточная часть УПД (перенос с rsbu.invoice) ---
    upd_shipper_id = fields.Many2one(
        'res.partner', string='Грузоотправитель',
        help='Грузоотправитель для УПД (ГрузОт/ГрузОтпр). Если не задан — '
             'совпадает с продавцом («он же»).')
    upd_consignee_id = fields.Many2one(
        'res.partner', string='Грузополучатель',
        help='Грузополучатель для УПД (ГрузПолуч). Если не задан — '
             'совпадает с покупателем.')
    upd_transferred_by_id = fields.Many2one(
        'res.users', string='Передал (кладовщик)',
        help='Лицо, ответственное за передачу товаров/услуг со стороны '
             'продавца (СвПродПер/СвЛицПер/РабОргПрод в УПД).')
    upd_received_by_id = fields.Many2one(
        'res.users', string='Принял груз',
        help='Лицо, принявшее груз со стороны покупателя. Отражается в '
             'документе о приёмке (файл покупателя ON_NSCHFDOPPOK).')
    upd_transport = fields.Char(
        string='Данные о транспортировке',
        help='Сведения о транспортировке и грузе (Тран/СвТран в УПД).')
    upd_basis = fields.Char(
        string='Основание передачи',
        help='Основание (договор, накладная и т.п.) — ОснПер в УПД. Если '
             'не задано — берётся договор/номер документа-источника.')
    upd_operation_content = fields.Char(
        string='Содержание операции', default='Товары/услуги переданы',
        help='Содержание операции передачи (СвПер/СодОпер в УПД).')

    # Связь 1 — 0..1 с отгрузочным СФ (порождённым при наличии НДС).
    invoice_id = fields.Many2one(
        'rsbu.invoice', string='Счёт-фактура (при НДС)', copy=False,
        ondelete='set null')

    # Налоговая сводка строк (питает суммовые итоги УПД).
    amount_untaxed = fields.Monetary(string='База (без НДС)',
                                     currency_field='currency_id')
    amount_tax = fields.Monetary(string='НДС всего',
                                 currency_field='currency_id')

    upd_function = fields.Selection(
        selection=[('1', 'СЧФДОП'), ('2', 'ДОП')],
        string='Функция УПД', compute='_compute_upd_function')

    @api.depends('company_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id

    @api.depends('invoice_id')
    def _compute_upd_function(self):
        for rec in self:
            rec.upd_function = '1' if rec.invoice_id else '2'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                seq = self.env['ir.sequence'].with_company(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = seq.next_by_code('rsbu.realization') or '/'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Связь с инвойсом-источником (для товарных позиций УПД, Вариант B)
    # ------------------------------------------------------------------
    def _source_invoice(self):
        """Вернуть документ-источник (account.move), если задан.

        Товарные позиции УПД (наименование/кол-во/ОКЕИ/ГТИН) берутся из
        инвойса Odoo, а финансовые показатели — из РСБУ-слоя (Вариант B).
        """
        self.ensure_one()
        if self.source_model == 'account.move' and self.source_res_id:
            move = self.env['account.move'].browse(self.source_res_id)
            return move if move.exists() else self.env['account.move']
        return self.env['account.move']

    # ------------------------------------------------------------------
    # Наличие НДС, выбор ставки, порождение отгрузочного СФ
    # ------------------------------------------------------------------
    @api.model
    def _has_vat(self, move):
        """True ⇔ в документе есть ФАКТИЧЕСКИЙ выходной НДС.

        Единственный источник истины — вычисленная compute_all сумма налога
        по строкам источника. Устойчиво к price_include (спецставки УСН
        «в том числе» 5/7% опознаются как облагаемые). НЕ использовать
        price_total != price_subtotal и НЕ кредит vat_output как детектор.
        """
        for line in move.invoice_line_ids.filtered(
                lambda l: l.display_type in (False, 'product')):
            if not line.tax_ids:
                continue
            res = line.tax_ids.compute_all(
                line.price_unit, quantity=line.quantity,
                currency=line.currency_id, product=line.product_id,
                partner=line.partner_id)
            if any(t.get('amount') for t in res['taxes']):
                return True
        return False

    @api.model
    def _upd_vat_rate(self, move):
        """Ставка vat_rate СФ по ФАКТИЧЕСКИМ налогам строк источника.

        Отображает процент налога на селектор rsbu.invoice.vat_rate. При
        смешанных ставках берётся максимальная ненулевая (консервативно для
        отчётности, Q7). Нет ненулевых налогов → vat_exempt.
        """
        percents = []
        for line in move.invoice_line_ids.filtered(
                lambda l: l.display_type in (False, 'product')):
            for tax in line.tax_ids:
                if tax.amount:
                    percents.append(tax.amount)
        if not percents:
            return 'vat_exempt'
        top = max(percents)
        for pct, rate in _PCT_TO_VAT_RATE:
            if abs(top - pct) < 0.01:
                return rate
        return 'vat_exempt'

    def _upd_advance_offset(self):
        """Данные зачёта аванса из РСБУ-проводки реализации.

        Возвращает (origin_move, offset_amount): проводка-аванс, зачтённая
        этой отгрузкой (первое основание), и общая сумма зачёта. Проводку
        читаем через источник — у rsbu.realization нет rsbu_move_id (Q6).
        """
        self.ensure_one()
        move = self._source_invoice().rsbu_move_id
        if not move:
            return self.env['rsbu.move'], 0.0
        advance_acc = self.env['rsbu.invoice'].sudo(
        )._role_account_for_company('advance_received', self.company_id)
        if not advance_acc:
            return self.env['rsbu.move'], 0.0
        offset_lines = move.line_ids.filtered(
            lambda l: l.account_id == advance_acc and l.debit > 0
            and l.origin_move_id)
        origin = offset_lines[:1].origin_move_id
        total = sum(offset_lines.mapped('debit'))
        return origin, total

    def _upd_vat_amount(self):
        """Сумма НДС реализации из РСБУ-проводки (Кт счёта vat_output).

        Фолбэк — amount_tax реализации, если проводки нет. vat_output —
        ИСТОЧНИК СУММЫ, не детектор наличия НДС (детектор — _has_vat).
        """
        self.ensure_one()
        move = self._source_invoice().rsbu_move_id
        vat_accounts = self.env['rsbu.vat.book.line'].sudo(
        )._vat_output_accounts(self.company_id)
        if move and vat_accounts:
            credit = sum(move.line_ids.filtered(
                lambda l: l.account_id in vat_accounts and l.credit > 0
            ).mapped('credit'))
            if credit:
                return credit
        return abs(self.amount_tax)

    def _create_shipment_invoice(self):
        """Создать подчинённый отгрузочный СФ (rsbu.invoice, shipment).

        Вызывается при наличии НДС (_has_vat). Инвариант INV-1: у реализации
        не более одного активного отгрузочного СФ.
        """
        self.ensure_one()
        if self.invoice_id and self.invoice_id.state != 'cancelled':
            raise UserError(_(
                'По этому документу реализации уже выписан счёт-фактура: '
                '%s.') % self.invoice_id.name)
        move = self._source_invoice()
        origin_move, _offset = self._upd_advance_offset()
        vals = {
            'invoice_type': 'shipment',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'date': self.date or fields.Date.context_today(self),
            'vat_rate': self._upd_vat_rate(move) if move else 'vat_exempt',
            'base_amount': abs(self.amount_untaxed),
            'vat_amount': self._upd_vat_amount(),
            'source_model': 'account.move',
            'source_res_id': self.source_res_id,
            'realization_id': self.id,
        }
        if origin_move:
            vals['origin_move_id'] = origin_move.id
        invoice = self.env['rsbu.invoice'].sudo().create(vals)
        invoice.action_confirm()
        self.invoice_id = invoice
        return invoice

    # ------------------------------------------------------------------
    # Сброс статуса закрывающего документа у инвойса-источника
    # ------------------------------------------------------------------
    def _upd_reset_source_move(self):
        """При отмене/удалении реализации вернуть closing_document источника
        в «Не сделан»."""
        Move = self.env['account.move'].sudo()
        for rec in self.filtered(lambda r: r.source_model == 'account.move'
                                 and r.source_res_id):
            move = Move.browse(rec.source_res_id)
            if move.exists() and move.closing_document != 'not_done':
                move.closing_document = 'not_done'

    def action_cancel(self):
        self._upd_reset_source_move()
        return self.write({'state': 'cancelled'})

    def unlink(self):
        self._upd_reset_source_move()
        return super().unlink()

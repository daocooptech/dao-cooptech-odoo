from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class RsbuMove(models.Model):
    """Хозяйственная операция РСБУ (аналог account.move)."""
    _name = 'rsbu.move'
    _description = 'РСБУ — Хозяйственная операция'
    _order = 'date desc, name desc, id desc'
    _check_company_auto = True
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Номер', default='/', copy=False, readonly=True, index=True)
    date = fields.Date(
        string='Дата операции', required=True, index=True,
        default=fields.Date.context_today, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True, index=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        compute='_compute_currency_id', store=True)
    state = fields.Selection(
        selection=[('draft', 'Черновик'), ('posted', 'Проведён')],
        string='Состояние', default='draft', required=True,
        copy=False, tracking=True, index=True)
    line_ids = fields.One2many(
        'rsbu.move.line', 'move_id', string='Строки проводки',
        copy=True)
    ref = fields.Char(string='Ссылка / описание')
    note = fields.Text(string='Примечание')

    # Ссылка на документ-источник (используется Этапом 3).
    source_model = fields.Char(string='Модель источника', copy=False)
    source_res_id = fields.Integer(string='ID источника', copy=False)

    # Контрольные обороты по проводке (для проверки баланса, не «сумма
    # операции»): при наличии внутренних проводок (напр. НДС на 90.03)
    # оборот по дебету не равен сумме документа, поэтому «сумму операции»
    # намеренно не храним и не показываем.
    total_debit = fields.Monetary(
        string='Оборот Дт', compute='_compute_totals', store=True,
        currency_field='currency_id')
    total_credit = fields.Monetary(
        string='Оборот Кт', compute='_compute_totals', store=True,
        currency_field='currency_id')
    line_count = fields.Integer(
        string='Кол-во строк', compute='_compute_line_count')

    # Красное сторно: отмена документа-источника не удаляет проведённую
    # операцию, а гасит её такой же с обратным знаком сумм.
    reversed_move_id = fields.Many2one(
        'rsbu.move', string='Сторнирует', copy=False, readonly=True,
        index=True, ondelete='restrict')
    reversal_move_ids = fields.One2many(
        'rsbu.move', 'reversed_move_id', string='Сторно')

    # ------------------------------------------------------------------
    # Вычисляемые поля
    # ------------------------------------------------------------------
    @api.depends('company_id')
    def _compute_currency_id(self):
        for move in self:
            move.currency_id = move.company_id.currency_id

    @api.depends('line_ids.debit', 'line_ids.credit')
    def _compute_totals(self):
        for move in self:
            move.total_debit = sum(move.line_ids.mapped('debit'))
            move.total_credit = sum(move.line_ids.mapped('credit'))

    @api.depends('line_ids')
    def _compute_line_count(self):
        for move in self:
            move.line_count = len(move.line_ids)

    # ------------------------------------------------------------------
    # Проверки при проведении
    # ------------------------------------------------------------------
    def _check_has_lines(self):
        for move in self:
            if not move.line_ids:
                raise UserError(_(
                    'Нельзя провести операцию «%s» без строк.')
                    % move.display_name)

    def _check_balanced(self):
        for move in self:
            rounding = move.currency_id.rounding or 0.01
            total_debit = sum(move.line_ids.mapped('debit'))
            total_credit = sum(move.line_ids.mapped('credit'))
            if not float_is_zero(total_debit - total_credit,
                                 precision_rounding=rounding):
                raise UserError(_(
                    'Операция «%(name)s» не сбалансирована: '
                    'дебет %(debit)s ≠ кредит %(credit)s.',
                    name=move.display_name,
                    debit=total_debit, credit=total_credit))

    def _check_required_subconto(self):
        for move in self:
            for line in move.line_ids:
                required = line.account_id.get_required_subconto()
                missing = [dim for dim in required
                           if not line._has_subconto(dim)]
                if missing:
                    labels = {'partner': 'Контрагент', 'product': 'Номенклатура',
                              'user': 'Пользователь', 'employee': 'Сотрудник'}
                    names = ', '.join(labels.get(m, m) for m in missing)
                    raise UserError(_(
                        'Строка со счётом «%(acc)s» требует обязательные '
                        'субконто: %(subs)s.',
                        acc=line.account_id.display_name, subs=names))

    # ------------------------------------------------------------------
    # Жизненный цикл
    # ------------------------------------------------------------------
    def _check_period_open(self, date=None):
        """Дата операции позже даты закрытия периода её компании."""
        for move in self:
            lock = move.company_id.rsbu_lock_date
            check = fields.Date.to_date(date or move.date)
            if lock and check and check <= lock:
                raise UserError(_(
                    'Период РСБУ организации «%(company)s» закрыт по '
                    '%(lock)s: операцию от %(date)s нельзя провести, '
                    'вернуть в черновик или сторнировать этой датой.',
                    company=move.company_id.name,
                    lock=fields.Date.to_string(lock),
                    date=fields.Date.to_string(check)))

    def _reverse(self):
        """Сторнировать проведённые операции (красное сторно).

        Дата сторно — дата операции, если её период открыт, иначе сегодня:
        закрытый период не трогаем.
        """
        reversals = self.browse()
        for move in self:
            if move.state != 'posted':
                raise UserError(_(
                    'Сторнировать можно только проведённую операцию «%s».')
                    % move.display_name)
            if move.reversal_move_ids:
                raise UserError(_(
                    'Операция «%s» уже сторнирована.') % move.display_name)
            lock = move.company_id.rsbu_lock_date
            date = move.date
            if lock and date <= lock:
                date = fields.Date.context_today(move)
            lines = []
            for line in move.line_ids:
                vals = line.copy_data()[0]
                vals.pop('move_id', None)
                vals['debit'] = -line.debit
                vals['credit'] = -line.credit
                lines.append((0, 0, vals))
            reversal = self.create({
                'date': date,
                'company_id': move.company_id.id,
                'ref': _('Сторно %s', move.name),
                'source_model': move.source_model,
                'source_res_id': move.source_res_id,
                'reversed_move_id': move.id,
                'line_ids': lines,
            })
            reversal.action_post()
            reversals |= reversal
        return reversals

    def action_post(self):
        for move in self:
            if move.state == 'posted':
                continue
            move._check_period_open()
            move._check_has_lines()
            move._check_balanced()
            move._check_required_subconto()
            if move.name == '/' or not move.name:
                move.name = self.env['ir.sequence']._rsbu_next_for_company(
                    'rsbu_journal.seq_rsbu_move', move.company_id, move.date)
            move.state = 'posted'
        return True

    def action_draft(self):
        for move in self:
            if move.state == 'posted':
                move._check_period_open()
            move.state = 'draft'
        return True

    def write(self, vals):
        # Ограничение редактирования ключевых полей у проведённой операции.
        protected = {'line_ids', 'date', 'company_id'}
        if any(f in vals for f in protected):
            for move in self:
                if move.state == 'posted':
                    raise UserError(_(
                        'Операция «%s» проведена. Верните её в черновик '
                        'перед изменением строк или даты.')
                        % move.display_name)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        for move in self:
            if move.state == 'posted':
                raise UserError(_(
                    'Нельзя удалить проведённую операцию «%s». '
                    'Сначала верните её в черновик.') % move.display_name)

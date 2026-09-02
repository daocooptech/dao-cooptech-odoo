# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopShareAccount(models.Model):
    """Паевой счёт в одном кооперативе.

    Паевой счёт — не кошелёк: пай нельзя потратить внутри платформы. Он
    показывает долю участника в кооперативе — сколько внесено, что
    начислено по итогам работы и что выплачено на руки.

    Счёт свой в каждом кооперативе, и это не техническая подробность: у
    каждого свой устав, свои правила начисления и свой порядок возврата
    пая при выходе. Сводить их в одну сумму можно только справочно —
    вынуть её одним действием нельзя.

    Счёт не прячется при выходе из кооператива. По уставам пай
    возвращается в течение года после утверждения годового отчёта: экран
    нужен ровно тогда, когда членство уже закончилось.
    """
    _name = 'coop.share.account'
    _description = 'Паевой счёт'
    _inherit = ['mail.thread']
    _order = 'state, id'
    _rec_name = 'display_name'

    wallet_id = fields.Many2one(
        'coop.wallet', string='Кошелёк', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        related='wallet_id.partner_id', store=True, index=True, string='Пайщик')
    cooperative_id = fields.Many2one(
        'res.partner', string='Кооператив', required=True, index=True,
        ondelete='restrict', domain=[('is_company', '=', True)])
    membership_id = fields.Many2one(
        'coop.membership', string='Членство', index=True,
        help='Пай существует, пока есть членство: счёт без него — запись '
             'ни о чём.')
    display_name = fields.Char(compute='_compute_display_name', store=True)

    joined_on = fields.Date(string='Пайщик с')
    currency_id = fields.Many2one(related='wallet_id.currency_id', store=True)

    move_ids = fields.One2many('coop.share.move', 'account_id', string='Движения')

    # Четыре величины из макета. Считаются по виду операции, а не
    # хранятся: текущий пай — их сумма, и вторая копия разошлась бы с
    # историей при первой же правке.
    contributed = fields.Monetary(
        string='Паевые взносы', currency_field='currency_id',
        compute='_compute_totals', store=True)
    accrued = fields.Monetary(
        string='Начислено', currency_field='currency_id',
        compute='_compute_totals', store=True)
    paid_out = fields.Monetary(
        string='Выплачено на руки', currency_field='currency_id',
        compute='_compute_totals', store=True)
    balance = fields.Monetary(
        string='Текущий пай', currency_field='currency_id',
        compute='_compute_totals', store=True)

    state = fields.Selection([
        ('open', 'Действующий'),
        ('closing', 'К возврату'),
        ('closed', 'Возвращён'),
    ], string='Состояние', default='open', required=True, index=True,
        tracking=True,
        help='«К возврату» — членство прекращается, а пай ещё не выплачен. '
             'Именно в этом состоянии счёт нужнее всего.')

    # Правило начисления берётся из устава кооператива, а не из настроек
    # платформы. У трёх кооперативов в макете три разные механики — по
    # труду, по обороту через кооператив и по размеру вклада, — и это не
    # разнообразие ради разнообразия, а разные виды кооперации.
    charter_note = fields.Text(
        string='Правило устава',
        help='Как в этом кооперативе начисляется выплата и как возвращается '
             'пай при выходе.')

    _sql_constraints = [
        ('one_per_coop', 'unique(wallet_id, cooperative_id)',
         'Паевой счёт в этом кооперативе уже есть.'),
    ]

    @api.depends('cooperative_id', 'partner_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.cooperative_id.display_name or ''

    @api.depends('move_ids.amount', 'move_ids.kind', 'move_ids.state')
    def _compute_totals(self):
        for record in self:
            confirmed = record.move_ids.filtered(lambda m: m.state == 'confirmed')
            record.contributed = sum(confirmed.filtered(
                lambda m: m.kind in ('entry', 'share', 'extra', 'in_kind')).mapped('amount'))
            record.accrued = sum(confirmed.filtered(
                lambda m: m.kind == 'accrual').mapped('amount'))
            record.paid_out = -sum(confirmed.filtered(
                lambda m: m.kind in ('payout', 'return')).mapped('amount'))
            record.balance = sum(confirmed.mapped('amount'))

    def action_request_payout(self):
        """Подать заявление на выплату.

        Заявление — не сама выплата: её решает орган управления по уставу.
        Кнопка заводит движение в состоянии «заявлено», и оно не входит в
        пай, пока решение не принято.
        """
        self.ensure_one()
        self.partner_id.coop_require_level('identity', _('подать заявление на выплату'))
        if self.state == 'closed':
            raise UserError(_('Пай уже возвращён — заявлять не о чем.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Заявление на выплату'),
            'res_model': 'coop.share.move',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_account_id': self.id,
                'default_kind': 'payout',
                'default_state': 'requested',
                'default_basis': _('Заявление участника'),
            },
        }


class CoopShareMove(models.Model):
    """Движение по паевому счёту.

    У каждого движения есть основание, и это не формальность: размер пая
    меняется решением органа управления. Запись без ссылки на решение не
    значит ничего, и обнаружится это ровно тогда, когда пайщик придёт за
    возвратом пая.

    Взноса трудом не бывает: пай — имущественный взнос. Труд участника
    учитывается отдельно и влияет на начисление по итогам работы, а не на
    размер пая.
    """
    _name = 'coop.share.move'
    _description = 'Движение по паевому счёту'
    _inherit = ['mail.thread']
    _order = 'date, id'

    account_id = fields.Many2one(
        'coop.share.account', string='Паевой счёт', required=True, index=True,
        ondelete='cascade')
    date = fields.Date(
        string='Дата', required=True, default=fields.Date.context_today, index=True)
    name = fields.Char(string='Операция', required=True)

    kind = fields.Selection([
        ('entry', 'Вступительный взнос'),
        ('share', 'Паевой взнос'),
        ('extra', 'Дополнительный паевой взнос'),
        ('in_kind', 'Взнос имуществом'),
        ('accrual', 'Начисление по итогам работы'),
        ('payout', 'Выплата на руки'),
        ('return', 'Возврат пая при выходе'),
    ], string='Вид', required=True, default='share', index=True)

    amount = fields.Monetary(
        string='Сумма', currency_field='currency_id', required=True,
        help='Плюс — пай вырос, минус — уменьшился.')
    currency_id = fields.Many2one(related='account_id.currency_id', store=True)

    basis = fields.Char(
        string='Основание', required=True,
        help='Протокол общего собрания № 4, решение правления, заявление '
             'участника.')
    valuation_basis = fields.Char(
        string='Основание оценки',
        help='Для взноса имуществом: чем подтверждена его стоимость. Без '
             'этого доля вносящего берётся с его слов.')

    state = fields.Selection([
        ('requested', 'Заявлено'),
        ('confirmed', 'Проведено'),
        ('declined', 'Отклонено'),
    ], string='Состояние', default='confirmed', required=True, index=True,
        tracking=True)

    balance_after = fields.Monetary(
        string='Пай после операции', currency_field='currency_id',
        compute='_compute_balance_after',
        help='Считается по порядку дат. Хранить отдельно нельзя: '
             'вставленная задним числом операция сдвинет весь столбец.')

    _sql_constraints = [
        ('amount_not_zero', 'check(amount != 0)',
         'Движение на ноль не имеет смысла.'),
    ]

    @api.depends('account_id.move_ids.amount', 'date', 'state')
    def _compute_balance_after(self):
        for record in self:
            if not record.account_id:
                record.balance_after = 0
                continue
            earlier = record.account_id.move_ids.filtered(
                lambda m: m.state == 'confirmed'
                and (m.date or fields.Date.today(), m.id)
                <= (record.date or fields.Date.today(), record.id))
            record.balance_after = sum(earlier.mapped('amount'))

    @api.constrains('kind', 'valuation_basis', 'state')
    def _check_in_kind(self):
        for record in self:
            if record.kind == 'in_kind' and record.state == 'confirmed' \
                    and not record.valuation_basis:
                raise ValidationError(_(
                    'У взноса имуществом должно быть указано основание '
                    'оценки. Иначе доля вносящего берётся с его слов, а её '
                    'оплачивают все остальные размытием своих долей.'))

    def action_confirm(self):
        self.write({'state': 'confirmed'})
        return True

    def action_decline(self):
        self.write({'state': 'declined'})
        return True

    def unlink(self):
        confirmed = self.filtered(lambda m: m.state == 'confirmed')
        if confirmed:
            raise UserError(_(
                'Проведённое движение по паю не удаляется: это история '
                'членских отношений. Ошибку исправляют встречным движением '
                'с указанием основания.'))
        return super().unlink()

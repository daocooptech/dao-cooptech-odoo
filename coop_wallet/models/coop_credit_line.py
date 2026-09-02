# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopCreditLine(models.Model):
    """Линия взаимного кредита с одним названным контрагентом.

    Здесь я сначала сделал неправильно, и стоит записать почему.
    Взаимный кредит — не общий котёл и не один баланс участника. Это
    **обязательства между двумя названными сторонами**: поставили товар и
    не получили денег сразу — у одного возникло требование к другому, у
    другого встречное обязательство. Ничего не выпускается и не
    эмитируется; ведётся учёт встречных требований, которые потом гасятся
    деньгами или взаимозачётом.

    Из этого следует всё остальное:

    - **насколько можно уйти в минус, решает кредитор**, а не платформа:
      ждать соглашается он, ему и определять, сколько ждать. Общий лимит
      «от платформы» сделал бы её стороной отношений, которой она не
      является;
    - **каждое изменение сальдо подтверждают обе стороны**. По сути это
      акт сверки после каждой операции, и переписать историю в одиночку
      нельзя;
    - линия хранится **один раз на пару**, в направлении «кто завёл → к
      кому». Хранить обе стороны значит немедленно получить их
      расхождение — так же, как с дружбой.

    Единица — кредит: примерно час труда или эквивалент по договорённости
    сторон. Курса у неё нет и быть не может: как только у единицы
    появляется курс и её начинают принимать где угодно, это уже денежный
    суррогат.
    """
    _name = 'coop.credit.line'
    _description = 'Линия взаимного кредита'
    _inherit = ['mail.thread']
    _order = 'balance, id'
    _rec_name = 'display_name'

    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True,
        ondelete='cascade')
    counterparty_id = fields.Many2one(
        'res.partner', string='Контрагент', required=True, index=True,
        ondelete='cascade')
    display_name = fields.Char(compute='_compute_display_name', store=True)

    # Знак — от лица участника: плюс, если контрагент должен ему.
    balance = fields.Float(
        string='Сальдо, кредитов', compute='_compute_balance', store=True,
        help='Плюс — контрагент должен вам, минус — вы ему.')

    # Лимит ставит тот, кто соглашается ждать. Поэтому их два: сколько
    # готов ждать участник и сколько готов ждать контрагент.
    limit_by_partner = fields.Float(
        string='Ваш лимит доверия', default=100.0, tracking=True,
        help='На сколько кредитов вы готовы уйти в плюс по отношению к '
             'контрагенту — то есть подождать. Ставите вы, потому что '
             'ждёте вы.')
    limit_by_counterparty = fields.Float(
        string='Лимит контрагента', default=100.0, tracking=True)

    movement_ids = fields.One2many(
        'coop.credit.movement', 'line_id', string='Операции')
    movement_count = fields.Integer(
        string='Операций', compute='_compute_balance', store=True)
    last_movement_on = fields.Date(
        string='Последняя операция', compute='_compute_balance', store=True)

    active = fields.Boolean(string='Действующая', default=True)

    _sql_constraints = [
        ('pair_uniq', 'unique(partner_id, counterparty_id)',
         'Линия с этим контрагентом уже заведена.'),
        ('not_self', 'check(partner_id != counterparty_id)',
         'Линия взаимного кредита с самим собой не имеет смысла.'),
    ]

    @api.constrains('partner_id', 'counterparty_id')
    def _check_reverse(self):
        """Запретить встречную линию по той же паре.

        Иначе у двоих окажется два сальдо, и они разойдутся при первой же
        операции — а спорить будут о том, какое из них верное.
        """
        for record in self:
            reverse = self.with_context(active_test=False).search_count([
                ('partner_id', '=', record.counterparty_id.id),
                ('counterparty_id', '=', record.partner_id.id),
            ])
            if reverse:
                raise ValidationError(_(
                    'Линия между этими участниками уже есть — встречную '
                    'заводить не нужно, сальдо у неё одно на двоих.'))

    @api.depends('partner_id', 'counterparty_id')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s ↔ %s' % (
                record.partner_id.display_name or '',
                record.counterparty_id.display_name or '')

    @api.depends('movement_ids.amount', 'movement_ids.state', 'movement_ids.date')
    def _compute_balance(self):
        for record in self:
            confirmed = record.movement_ids.filtered(
                lambda m: m.state == 'confirmed')
            record.balance = sum(confirmed.mapped('amount'))
            record.movement_count = len(record.movement_ids)
            dates = confirmed.mapped('date')
            record.last_movement_on = max(dates) if dates else False

    @api.model
    def line_for(self, partner, counterparty):
        """Найти линию пары или завести её.

        Направление хранения не важно для смысла и важно для данных:
        линия одна, а знак сальдо читается от того, кто на неё смотрит.
        """
        Line = self.sudo()
        line = Line.with_context(active_test=False).search([
            ('partner_id', '=', partner.id),
            ('counterparty_id', '=', counterparty.id),
        ], limit=1)
        if line:
            return line
        line = Line.with_context(active_test=False).search([
            ('partner_id', '=', counterparty.id),
            ('counterparty_id', '=', partner.id),
        ], limit=1)
        if line:
            return line
        return Line.create({
            'partner_id': partner.id,
            'counterparty_id': counterparty.id,
        })


class CoopCreditMovement(models.Model):
    """Операция по линии взаимного кредита.

    Подтверждают обе стороны. Пока подтверждения нет, операция в сальдо
    не входит: односторонняя запись «ты мне должен» не создаёт долга ни
    в жизни, ни здесь.
    """
    _name = 'coop.credit.movement'
    _description = 'Операция взаимного кредита'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    line_id = fields.Many2one(
        'coop.credit.line', string='Линия', required=True, index=True,
        ondelete='cascade')
    date = fields.Date(
        string='Дата', required=True, default=fields.Date.context_today, index=True)
    name = fields.Char(
        string='За что', required=True,
        help='«Помощь с монтажом каркаса теплицы, 3 часа».')
    amount = fields.Float(
        string='Кредитов', required=True,
        help='Плюс — в вашу пользу, минус — в пользу контрагента. '
             'Кредит — примерно час труда или эквивалент по '
             'договорённости сторон.')

    state = fields.Selection([
        ('proposed', 'Предложено'),
        ('confirmed', 'Подтверждено обеими'),
        ('declined', 'Отклонено'),
        ('offset', 'Погашено взаимозачётом'),
    ], string='Состояние', default='proposed', required=True, index=True,
        tracking=True)

    proposed_by_id = fields.Many2one(
        'res.partner', string='Предложил', readonly=True,
        default=lambda self: self.env.user._coop_acting_partner())
    confirmed_by_id = fields.Many2one(
        'res.partner', string='Подтвердил', readonly=True)
    confirmed_on = fields.Date(string='Когда подтверждено', readonly=True)

    deal_id = fields.Many2one('coop.deal', string='Сделка', index=True)
    clearing_id = fields.Many2one(
        'coop.credit.clearing', string='Взаимозачёт', index=True, readonly=True)

    _sql_constraints = [
        ('amount_not_zero', 'check(amount != 0)',
         'Операция на ноль кредитов не имеет смысла.'),
    ]

    def action_confirm(self):
        """Подтвердить со своей стороны.

        Подтверждает не тот, кто предложил: смысл в том, что запись
        признают обе стороны. Иначе это не акт сверки, а односторонняя
        запись в чужой долг.
        """
        me = self.env.user._coop_acting_partner()
        for record in self:
            if record.proposed_by_id == me:
                raise UserError(_(
                    'Подтверждает вторая сторона. Своё же предложение '
                    'подтверждать нечем: тогда это не сверка, а запись в '
                    'чужой долг.'))
            if me not in (record.line_id.partner_id, record.line_id.counterparty_id):
                raise UserError(_('Это чужая линия взаимного кредита.'))
            record.write({
                'state': 'confirmed',
                'confirmed_by_id': me.id,
                'confirmed_on': fields.Date.context_today(record),
            })
        return True

    def action_decline(self):
        self.write({'state': 'declined'})
        return True


class CoopCreditClearing(models.Model):
    """Взаимозачёт по кругу.

    Когда долги замыкаются в кольцо — вы должны одному, он второму, тот
    вам, — их можно погасить встречно, ничего не передавая. Гасится
    минимальное звено круга: на эту величину ни один баланс не
    ухудшается, и это свойство зачёта, а не наша щедрость.

    Зачёт не проводится сам. Платформа предлагает круг и собирает подписи
    всех участников; **не подписал хотя бы один — раунд отменяется
    целиком**. Частичного зачёта не бывает: подписав, участник согласился
    на кольцо, а не на его часть.
    """
    _name = 'coop.credit.clearing'
    _description = 'Взаимозачёт по кругу'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Раунд', required=True, default='Новый круг')
    amount = fields.Float(
        string='Величина зачёта', required=True,
        help='Минимальное звено круга: больше зачесть нельзя, не ухудшив '
             'чей-то баланс.')
    participant_ids = fields.Many2many(
        'res.partner', string='Участники круга')
    line_ids = fields.Many2many('coop.credit.line', string='Звенья круга')
    signature_ids = fields.One2many(
        'coop.credit.signature', 'clearing_id', string='Подписи')

    state = fields.Selection([
        ('proposed', 'Предложен'),
        ('signed', 'Проведён'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', default='proposed', required=True, tracking=True)

    signed_count = fields.Integer(
        string='Подписали', compute='_compute_signed', store=True)
    required_count = fields.Integer(
        string='Нужно подписей', compute='_compute_signed', store=True)

    @api.depends('signature_ids.signed', 'participant_ids')
    def _compute_signed(self):
        for record in self:
            record.required_count = len(record.participant_ids)
            record.signed_count = len(record.signature_ids.filtered('signed'))

    def action_sign(self):
        """Подписать раунд за себя.

        Когда подписали все — зачёт проводится: по каждому звену
        появляется встречная операция на величину круга.
        """
        me = self.env.user._coop_acting_partner()
        for record in self:
            signature = record.signature_ids.filtered(
                lambda s: s.partner_id == me)
            if not signature:
                raise UserError(_('Вы не участник этого круга.'))
            signature.write({
                'signed': True,
                'signed_on': fields.Date.context_today(record),
            })
            if record.signed_count >= record.required_count:
                record._apply()
        return True

    def action_cancel(self):
        """Отменить раунд целиком.

        Частичного зачёта не бывает: участник соглашался на кольцо, а не
        на его часть, и гасить половину круга значило бы ухудшить чей-то
        баланс без его согласия.
        """
        self.write({'state': 'cancelled'})
        return True

    def _apply(self):
        Movement = self.env['coop.credit.movement'].sudo()
        for record in self:
            for line in record.line_ids:
                # Знак встречной операции противоположен сальдо линии:
                # зачёт уменьшает долг, а не увеличивает.
                sign = -1 if line.balance > 0 else 1
                Movement.create({
                    'line_id': line.id,
                    'name': _('Взаимозачёт по кругу'),
                    'amount': sign * record.amount,
                    'state': 'confirmed',
                    'confirmed_on': fields.Date.context_today(record),
                    'clearing_id': record.id,
                })
            record.state = 'signed'
            record.message_post(body=_(
                'Круг погашен на %s кредитов. Передачи кредитов не '
                'происходило.') % record.amount)
        return True


class CoopCreditSignature(models.Model):
    """Подпись участника под раундом взаимозачёта."""
    _name = 'coop.credit.signature'
    _description = 'Подпись под взаимозачётом'
    _order = 'id'

    clearing_id = fields.Many2one(
        'coop.credit.clearing', string='Раунд', required=True,
        ondelete='cascade', index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True)
    signed = fields.Boolean(string='Подписал')
    signed_on = fields.Date(string='Когда', readonly=True)

    _sql_constraints = [
        ('one_per_partner', 'unique(clearing_id, partner_id)',
         'Этот участник уже в списке подписантов.'),
    ]

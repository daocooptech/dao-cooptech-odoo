# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopBountyTask(models.Model):
    """Задание рабочей группы, которое может взять любой участник.

    Устроено как на бирже фриланса и по образцу баунти: рабочая группа
    публикует задачу с вознаграждением, участники подают заявки, менеджер
    сообщества утверждает исполнителя, тот сдаёт работу, менеджер её
    принимает — и только тогда токены зачисляются.

    Почему зачисление именно при приёмке, а не при сдаче. Между «я сделал»
    и «работа принята» помещается всё, ради чего приёмка и существует;
    зачислять раньше значит платить за заявление о работе, а не за работу.
    Отменить зачисление потом нельзя — движения токенов не удаляются, они
    и есть история.
    """
    _name = 'coop.bounty.task'
    _description = 'Задание за вознаграждение'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state, deadline, id desc'

    name = fields.Char(string='Задача', required=True, tracking=True)
    description = fields.Html(
        string='Что нужно сделать',
        help='Опишите результат, а не процесс: по этому тексту исполнитель '
             'поймёт, когда работа считается выполненной.')

    reward_tokens = fields.Integer(
        string='Вознаграждение, токенов', required=True, tracking=True,
        help='Зачисляется исполнителю в кошелёк после приёмки работы.')

    coop_specialization_id = fields.Many2one(
        'coop.specialization', string='Специализация',
        help='По ней задача находится теми, кто умеет её делать.')
    deadline = fields.Date(string='Срок', tracking=True)

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Опубликовано'),
        ('assigned', 'В работе'),
        ('submitted', 'Сдано на проверку'),
        ('accepted', 'Принято'),
        ('cancelled', 'Отменено'),
    ], string='Состояние', default='draft', required=True, tracking=True, index=True)

    manager_id = fields.Many2one(
        'res.users', string='Разместил', default=lambda self: self.env.user,
        tracking=True, help='Менеджер сообщества, отвечающий за задачу.')
    assignee_id = fields.Many2one(
        'res.partner', string='Исполнитель', tracking=True, index=True,
        help='Утверждается менеджером из числа подавших заявку.')

    application_ids = fields.One2many(
        'coop.bounty.application', 'task_id', string='Заявки')
    application_count = fields.Integer(
        string='Заявок', compute='_compute_application_count')

    accepted_on = fields.Date(string='Принято', readonly=True)
    reward_transaction_id = fields.Many2one(
        'coop.token.transaction', string='Начисление', readonly=True,
        help='Движение токенов, которым выплачено вознаграждение.')

    # Признаки для интерфейса. Считаются относительно текущего
    # пользователя, поэтому не хранимые: одна и та же задача выглядит
    # по-разному для менеджера, исполнителя и постороннего.
    my_application_state = fields.Selection([
        ('none', 'Заявки нет'),
        ('applied', 'Заявка подана'),
        ('approved', 'Вы исполнитель'),
        ('rejected', 'Заявка отклонена'),
    ], string='Моя заявка', compute='_compute_my_application')
    is_mine = fields.Boolean(string='Я исполнитель', compute='_compute_my_application')

    @api.depends('application_ids')
    def _compute_application_count(self):
        for record in self:
            record.application_count = len(record.application_ids)

    def _compute_my_application(self):
        me = self.env.user.partner_id
        for record in self:
            record.is_mine = record.assignee_id == me
            application = record.application_ids.filtered(
                lambda a: a.partner_id == me)[:1]
            record.my_application_state = application.state if application else 'none'

    # ── Действия менеджера сообщества ────────────────────────────────────

    def action_publish(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Опубликовать можно только черновик.'))
            if record.reward_tokens <= 0:
                raise UserError(_(
                    'У задачи без вознаграждения нет смысла: укажите, '
                    'сколько токенов получит исполнитель.'))
            record.state = 'published'
        return True

    def action_accept(self):
        """Принять работу и зачислить вознаграждение."""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('Принять можно только сданную работу.'))
            if not record.assignee_id:
                raise UserError(_('У задачи нет исполнителя.'))
            transaction = self.env['coop.token.transaction'].sudo().create({
                'partner_id': record.assignee_id.id,
                'amount': record.reward_tokens,
                'kind': 'grant',
                'description': _('Вознаграждение за задачу «%s»') % record.name,
                'res_model': record._name,
                'res_id': record.id,
            })
            record.write({
                'state': 'accepted',
                'accepted_on': fields.Date.context_today(record),
                'reward_transaction_id': transaction.id,
            })
            record.message_post(body=_(
                'Работа принята, начислено %(amount)s токенов.',
                amount=record.reward_tokens))
        return True

    def action_return_for_revision(self):
        """Вернуть на доработку — без списаний и без потери исполнителя."""
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('Вернуть можно только сданную работу.'))
            record.state = 'assigned'
        return True

    def action_cancel(self):
        for record in self:
            if record.state == 'accepted':
                raise UserError(_(
                    'Принятую работу отменить нельзя: вознаграждение уже '
                    'начислено, а движения токенов не удаляются.'))
            record.state = 'cancelled'
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state == 'accepted':
                raise UserError(_('Принятую задачу нельзя вернуть в черновик.'))
            record.write({'state': 'draft', 'assignee_id': False})
        return True

    # ── Действия участника ───────────────────────────────────────────────

    def action_apply(self):
        """Подать заявку на выполнение задачи."""
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Заявки принимаются только по опубликованным задачам.'))
        me = self.env.user.partner_id
        existing = self.application_ids.filtered(lambda a: a.partner_id == me)
        if existing:
            raise UserError(_('Вы уже подали заявку по этой задаче.'))
        self.env['coop.bounty.application'].sudo().create({
            'task_id': self.id,
            'partner_id': me.id,
        })
        self.message_post(body=_('Подана заявка: %s') % me.display_name)
        return True

    def action_submit(self):
        """Сдать работу на проверку."""
        self.ensure_one()
        if self.state != 'assigned':
            raise UserError(_('Сдать можно только задачу, взятую в работу.'))
        if self.assignee_id != self.env.user.partner_id:
            raise UserError(_('Сдать работу может только её исполнитель.'))
        self.state = 'submitted'
        return True


class CoopBountyApplication(models.Model):
    """Заявка участника на выполнение задачи.

    Отдельной записью, а не полем «желающие» у задачи: у заявки есть своё
    состояние и своя дата, и по отклонённым заявкам видно, кому уже
    отказывали. Без этого менеджер сообщества каждый раз выбирает вслепую.
    """
    _name = 'coop.bounty.application'
    _description = 'Заявка на задачу'
    _order = 'create_date desc'

    task_id = fields.Many2one(
        'coop.bounty.task', string='Задача', required=True,
        ondelete='cascade', index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True,
        ondelete='cascade', index=True)
    message = fields.Text(
        string='Сопроводительное письмо',
        help='Чем участник обосновывает, что справится.')
    state = fields.Selection([
        ('applied', 'Подана'),
        ('approved', 'Утверждена'),
        ('rejected', 'Отклонена'),
    ], string='Состояние', default='applied', required=True, index=True)

    _sql_constraints = [
        ('one_per_task', 'unique(task_id, partner_id)',
         'Участник уже подал заявку по этой задаче.'),
    ]

    def action_approve(self):
        """Утвердить исполнителя.

        Остальные заявки по задаче отклоняются автоматически: исполнитель
        один, и оставлять чужие заявки в состоянии «подана» значит держать
        людей в неведении.
        """
        for record in self:
            if record.task_id.state not in ('published', 'assigned'):
                raise UserError(_(
                    'Утвердить исполнителя можно только по опубликованной задаче.'))
            others = record.task_id.application_ids - record
            others.filtered(lambda a: a.state == 'applied').write({'state': 'rejected'})
            record.state = 'approved'
            record.task_id.write({
                'assignee_id': record.partner_id.id,
                'state': 'assigned',
            })
            record.task_id.message_post(body=_(
                'Исполнителем утверждён %s') % record.partner_id.display_name)
        return True

    def action_reject(self):
        for record in self:
            record.state = 'rejected'
            if record.task_id.assignee_id == record.partner_id:
                record.task_id.write({'assignee_id': False, 'state': 'published'})
        return True

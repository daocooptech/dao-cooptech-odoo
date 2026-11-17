# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Способы оплаты задачи (решения 515, 671 п. 7, 672). Один перечень на
# автора, исполнителя и налоговый реестр: `tokens` читает coop_tax, и
# значение менять нельзя.
PAYMENT_METHODS = [
    ('rub_offset', '₽ с зачётом токенами'),
    ('tokens', 'Токены платформы'),
    ('rub', '₽'),
    ('project_tokens', 'Токены проекта'),
    ('share', 'Доля в проекте'),
]

# Состояния, в которых сумма задачи платформы отложена в фонде.
RESERVED_STATES = ('published', 'assigned', 'submitted', 'dispute')

# Сколько дней автор может молчать после сдачи (решение 671 п. 4).
DISPUTE_AFTER_DAYS = 7


class CoopBountyTask(models.Model):
    """Задача, которую может взять любой участник.

    Автор — платформа или организация проекта — отмечает допустимые
    способы оплаты, участники подают заявки и выбирают в них один способ,
    автор утверждает исполнителя, тот сдаёт результат, автор принимает.
    Задача платформы оплачивается из фонда и публикуется только после
    резерва полной суммы; задачу проекта оплачивает сама организация —
    рублями, своими токенами (правом требования продукции) или долей.

    Почему зачисление именно при приёмке, а не при сдаче. Между «я сделал»
    и «результат принят» помещается всё, ради чего приёмка и существует;
    зачислять раньше значит платить за заявление, а не за результат.
    Отменить зачисление потом нельзя — движения токенов не удаляются, они
    и есть история. Молчание автора после сдачи — не приёмка: через семь
    дней открывается спор, его разбирает администратор платформы
    (решения 671 п. 4 и 194).
    """
    _name = 'coop.bounty.task'
    _description = 'Задача за вознаграждение'
    # Снимок по смыслу задания (решение 341). Прежде лицом карточки был
    # исполнитель, а у свободного задания — пустой квадрат: две трети
    # каталога без картинки.
    _inherit = ['mail.thread', 'mail.activity.mixin', 'coop.page.mixin', 'image.mixin', 'coop.media.mixin']
    _order = 'state, deadline, id desc'

    name = fields.Char(string='Задача', required=True, tracking=True)
    description = fields.Html(
        string='Что нужно сделать',
        help='Опишите результат, а не процесс: по этому тексту исполнитель '
             'поймёт, когда задача считается выполненной.')

    reward_tokens = fields.Integer(
        string='Сумма, ₽', tracking=True,
        help='Для токенов — столько же токенов: 1 токен = 1 ₽ (решение 249). '
             'Токены проекта — право требования его продукции или услуги на '
             'эту сумму. При оплате только долей сумма не нужна.')
    reward_rub = fields.Integer(
        string='Цена, ₽', compute='_compute_reward_rub',
        help='1 токен = 1 ₽ (решение 249).')

    payer_id = fields.Many2one(
        'res.partner', string='От чьего имени', tracking=True, index=True,
        default=lambda self: self.env.company.partner_id,
        domain=[('is_company', '=', True)],
        help='Платформа или организация проекта: она оплачивает задачу и '
             'по ней — налоговый агент.')
    payer_kind = fields.Selection([
        ('platform', 'Платформа'),
        ('project', 'Проект'),
    ], string='Кто платит', compute='_compute_payer_kind', store=True, index=True)
    project_id = fields.Many2one(
        'coop.project', string='Проект', index=True, tracking=True,
        help='Проект, для которого нужна задача. Платит организация проекта.')

    # Решение 671 п. 7: автор даёт выбор, исполнитель выбирает, в чём ему
    # удобнее принимать.
    allowed_method_ids = fields.Many2many(
        'coop.bounty.method', string='Допустимые способы оплаты',
        help='Из них исполнитель выберет один в заявке.')
    allows_share = fields.Boolean(compute='_compute_allows')
    allows_money = fields.Boolean(compute='_compute_allows')
    share_percent = fields.Float(
        string='Доля в проекте, %', digits=(5, 2), tracking=True,
        help='Форму доли определяет организация по закону своей страны.')
    share_cap = fields.Float(
        related='payer_id.coop_labor_share_cap', string='Потолок организации, %')
    payment_mode = fields.Selection(
        PAYMENT_METHODS, string='Выбранный способ', tracking=True, readonly=True,
        help='Способ, который исполнитель выбрал в заявке; закрепляется, '
             'когда автор утверждает исполнителя.')

    fund_id = fields.Many2one(
        'coop.bounty.fund', string='Фонд', readonly=True, index=True,
        help='Фонд платформы, в котором отложена сумма задачи.')
    fund_free = fields.Integer(related='fund_id.free', string='Свободно в фонде')

    coop_specialization_id = fields.Many2one(
        'coop.specialization', string='Специализация',
        help='По ней задача находится теми, кто умеет её делать.')
    deadline = fields.Date(string='Срок', tracking=True)

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Опубликовано'),
        ('assigned', 'В работе'),
        ('submitted', 'Сдано на проверку'),
        ('dispute', 'Спор'),
        ('accepted', 'Принято'),
        ('cancelled', 'Отменено'),
    ], string='Состояние', default='draft', required=True, tracking=True, index=True)

    manager_id = fields.Many2one(
        'res.users', string='Разместил', default=lambda self: self.env.user,
        tracking=True, help='Кто разместил задачу от имени автора.')
    assignee_id = fields.Many2one(
        'res.partner', string='Исполнитель', tracking=True, index=True,
        help='Утверждается автором из числа подавших заявку.')

    application_ids = fields.One2many(
        'coop.bounty.application', 'task_id', string='Заявки')
    application_count = fields.Integer(
        string='Заявок', compute='_compute_application_count')

    # Условия и ход задачи (№ 464): критерии приёмки, вопросы к заявке,
    # сдачи с версиями, отзывы после приёмки.
    criterion_ids = fields.One2many('coop.bounty.criterion', 'task_id', string='Критерии приёмки')
    criteria_count = fields.Integer(compute='_compute_criteria')
    criteria_done_count = fields.Integer(compute='_compute_criteria')
    question_ids = fields.One2many('coop.bounty.question', 'task_id', string='Вопросы к заявке')
    submission_ids = fields.One2many('coop.bounty.submission', 'task_id', string='Сдачи')
    review_ids = fields.One2many('coop.bounty.review', 'task_id', string='Отзывы')
    can_review = fields.Boolean(compute='_compute_can_review')
    city = fields.Char(
        string='Город', compute='_compute_city', store=True, index=True,
        help='Город проекта или организации. У задач платформы — пусто: их делают удалённо.')
    assigned_on = fields.Date(string='Взята в работу', readonly=True)
    reminded_on = fields.Date(string='Напомнили о сроке', readonly=True)

    submitted_on = fields.Date(string='Сдано', readonly=True)
    days_to_dispute = fields.Integer(
        string='Дней до спора', compute='_compute_days_to_dispute')
    dispute_on = fields.Date(string='Спор открыт', readonly=True)
    dispute_decision = fields.Text(
        string='Объяснение решения', readonly=True, tracking=True,
        help='Решение администратора платформы по спору — видно обеим сторонам.')
    accepted_on = fields.Date(string='Принято', readonly=True)
    reward_transaction_id = fields.Many2one(
        'coop.token.transaction', string='Начисление', readonly=True,
        help='Движение токенов, которым выплачена задача платформы.')

    # Признаки для интерфейса. Считаются относительно текущего
    # пользователя, поэтому не хранимые: одна и та же задача выглядит
    # по-разному для автора, исполнителя и постороннего.
    my_application_state = fields.Selection([
        ('none', 'Заявки нет'),
        ('applied', 'Заявка подана'),
        ('approved', 'Вы исполнитель'),
        ('rejected', 'Заявка отклонена'),
    ], string='Моя заявка', compute='_compute_my_application')
    is_mine = fields.Boolean(string='Я исполнитель', compute='_compute_my_application')
    is_arbiter = fields.Boolean(compute='_compute_is_arbiter')

    @api.depends('reward_tokens')
    def _compute_reward_rub(self):
        for record in self:
            record.reward_rub = record.reward_tokens

    @api.depends('payer_id')
    def _compute_payer_kind(self):
        platform = self.env.company.partner_id
        for record in self:
            record.payer_kind = 'platform' if (
                not record.payer_id or record.payer_id == platform) else 'project'

    @api.depends('allowed_method_ids')
    def _compute_allows(self):
        for record in self:
            codes = set(record.allowed_method_ids.mapped('code'))
            record.allows_share = 'share' in codes
            record.allows_money = bool(codes - {'share'})

    @api.depends('criterion_ids', 'criterion_ids.done')
    def _compute_criteria(self):
        for record in self:
            record.criteria_count = len(record.criterion_ids)
            record.criteria_done_count = len(record.criterion_ids.filtered('done'))

    @api.depends('payer_kind', 'project_id.city', 'payer_id.city')
    def _compute_city(self):
        for record in self:
            if record.payer_kind == 'platform':
                record.city = False
            else:
                record.city = record.project_id.city or record.payer_id.city or False

    @api.depends('state', 'review_ids', 'assignee_id')
    @api.depends_context('uid')
    def _compute_can_review(self):
        for record in self:
            record.can_review = bool(record.id and record._coop_my_review_side())

    def _coop_my_review_side(self):
        """Чей отзыв может оставить текущий человек: автор — об исполнителе,
        исполнитель — об авторе; пусто, если отзыв уже есть или задача не его."""
        self.ensure_one()
        if self.state != 'accepted' or not self.assignee_id:
            return False
        user = self.env.user
        sides = self.sudo().review_ids.mapped('side')
        if self.assignee_id == user.partner_id and 'executor' not in sides:
            return 'executor'
        if 'author' not in sides and (self.payer_id in user.coop_publisher_partner_ids
                                      or user.has_group('coop_bounty.group_coop_community_manager')):
            return 'author'
        return False

    @api.depends('application_ids')
    def _compute_application_count(self):
        for record in self:
            record.application_count = len(record.application_ids)

    @api.depends('state', 'submitted_on')
    def _compute_days_to_dispute(self):
        today = fields.Date.context_today(self)
        for record in self:
            if record.state == 'submitted' and record.submitted_on:
                left = (record.submitted_on + timedelta(days=DISPUTE_AFTER_DAYS) - today).days
                record.days_to_dispute = max(left, 0)
            else:
                record.days_to_dispute = 0

    def _compute_my_application(self):
        me = self.env.user.partner_id
        for record in self:
            record.is_mine = record.assignee_id == me
            application = record.application_ids.filtered(
                lambda a: a.partner_id == me)[:1]
            record.my_application_state = application.state if application else 'none'

    def _compute_is_arbiter(self):
        arbiter = self._coop_is_arbiter()
        for record in self:
            record.is_arbiter = arbiter

    @api.model
    def _coop_is_arbiter(self):
        """Спор разбирает администратор платформы (решение 194)."""
        user = self.env.user
        return user.has_group('coop_base.group_coop_platform') or user.has_group('base.group_system')

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.partner_id.is_company:
            self.payer_id = self.project_id.partner_id

    @api.onchange('payer_kind')
    def _onchange_payer_kind(self):
        # Способы другого вида автора не переносятся: токены платформы у
        # проекта и доля у платформы недопустимы (решение 672).
        self.allowed_method_ids = self.allowed_method_ids.filtered(
            lambda m: m.scope in ('both', self.payer_kind))

    def write(self, vals):
        # Сумма опубликованной задачи платформы отложена в фонде: поменять
        # её значит разойтись с резервом. Сначала — в черновик.
        if 'reward_tokens' in vals:
            locked = self.filtered(lambda t: t.payer_kind == 'platform'
                                   and t.state in RESERVED_STATES
                                   and t.reward_tokens != vals['reward_tokens'])
            if locked:
                raise UserError(_(
                    'Сумму опубликованной задачи платформы не меняют: она уже '
                    'отложена в фонде. Верните задачу в черновик.'))
        return super().write(vals)

    # ── Действия автора ─────────────────────────────────────────────────

    def _coop_check_publishable(self):
        self.ensure_one()
        methods = self.allowed_method_ids
        if not methods:
            raise UserError(_(
                'Отметьте хотя бы один способ оплаты: исполнитель выберет из них.'))
        foreign = methods.filtered(lambda m: m.scope not in ('both', self.payer_kind))
        if foreign:
            raise UserError(_(
                'Способ «%(method)s» недоступен для задач %(whom)s.',
                method=foreign[0].name,
                whom=_('платформы') if self.payer_kind == 'platform' else _('проектов')))
        if not self.criterion_ids:
            raise UserError(_(
                'Добавьте хотя бы один критерий приёмки: по ним примут результат '
                'и разберут спор.'))
        if self.allows_money and self.reward_tokens <= 0:
            raise UserError(_('Укажите сумму: сколько получит исполнитель.'))
        if self.allows_share:
            if self.share_percent <= 0:
                raise UserError(_('Укажите долю в проекте, %.'))
            cap = self.payer_id.coop_labor_share_cap
            if cap and self.share_percent > cap:
                raise UserError(_(
                    'Доля больше потолка организации (%(cap)s %%). Уменьшите '
                    'долю, чтобы опубликовать.', cap=cap))

    def _coop_reserve_fund(self):
        """Отложить сумму задачи платформы в фонде (решение 671 п. 3)."""
        self.ensure_one()
        Fund = self.env['coop.bounty.fund'].sudo()
        fund = self.fund_id or Fund._coop_current()
        if not fund:
            raise UserError(_(
                'Фонда задач платформы на сегодня нет: задачу платформы '
                'опубликовать не из чего.'))
        if fund.free < self.reward_tokens:
            raise UserError(_(
                'Не хватает фонда: нужно %(need)s токенов, свободно %(free)s. '
                'Уменьшите сумму.', need=self.reward_tokens, free=fund.free))
        self.fund_id = fund

    def action_publish(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Опубликовать можно только черновик.'))
            record._coop_check_publishable()
            if record.payer_kind == 'platform':
                record._coop_reserve_fund()
            record.state = 'published'
            self.env['coop.bounty.subscription']._coop_notify_new_task(record)
        return True

    def action_accept(self):
        """Принять результат и рассчитаться по выбранному способу."""
        for record in self:
            if record.state not in ('submitted', 'dispute'):
                raise UserError(_('Принять можно только сданный результат.'))
            if not record.assignee_id:
                raise UserError(_('У задачи нет исполнителя.'))
            open_points = record.criterion_ids.filtered(lambda c: not c.done)
            if open_points and not self.env.context.get('coop_bounty_force_accept'):
                raise UserError(_(
                    'Отметьте выполненные критерии — принять можно, когда выполнены '
                    'все. Не выполнено: %s. Иначе верните на доработку.',
                    '; '.join(open_points.mapped('name'))))
            values = {
                'state': 'accepted',
                'accepted_on': fields.Date.context_today(record),
            }
            if record.payer_kind == 'platform':
                transaction = self.env['coop.token.transaction'].sudo().create({
                    'partner_id': record.assignee_id.id,
                    'amount': record.reward_tokens,
                    'kind': 'grant',
                    'description': _('Задача «%s»') % record.name,
                    'res_model': record._name,
                    'res_id': record.id,
                })
                values['reward_transaction_id'] = transaction.id
                body = _('Результат принят, начислено %(amount)s токенов из фонда задач.',
                         amount=record.reward_tokens)
            else:
                # Платформа не сторона расчётов участников: рубли, токены
                # проекта и долю передаёт организация.
                body = _('Результат принят. Расчёт способом «%(method)s» проводит %(payer)s.',
                         method=dict(PAYMENT_METHODS).get(record.payment_mode, '—'),
                         payer=record.payer_id.display_name)
            record.write(values)
            record.submission_ids.sudo().filtered(lambda s: s.state == 'review').write({
                'state': 'accepted', 'reviewed_on': fields.Date.context_today(record)})
            record.message_post(body=body)
            (record.assignee_id | record.payer_id).sudo()._coop_recompute_deal_stats()
            self.env['coop.notification'].sudo()._notify(
                record.assignee_id,
                _('Результат по задаче «%s» принят. Оставьте отзыв об авторе — он '
                  'идёт в уровень доверия.') % record.name,
                record=record, kind='other')
        return True

    def action_return_for_revision(self):
        """Окно «Вернуть на доработку»: замечания пишутся к сдаче."""
        self.ensure_one()
        if self.state not in ('submitted', 'dispute'):
            raise UserError(_('Вернуть можно только сданный результат.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Вернуть на доработку'),
            'res_model': 'coop.bounty.return',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    def _coop_do_return(self, note):
        """Вернуть на доработку — без списаний и без потери исполнителя."""
        today = fields.Date.context_today(self)
        for record in self:
            if record.state not in ('submitted', 'dispute'):
                raise UserError(_('Вернуть можно только сданный результат.'))
            record.submission_ids.sudo().filtered(lambda s: s.state == 'review').write({
                'state': 'returned', 'review_note': note, 'reviewed_on': today})
            record.write({'state': 'assigned', 'submitted_on': False, 'reminded_on': False})
            record.message_post(body=_('Возвращено на доработку: %s') % note)
        return True

    def action_cancel(self):
        for record in self:
            if record.state == 'accepted':
                raise UserError(_(
                    'Принятую задачу отменить нельзя: расчёт уже проведён, а '
                    'движения токенов не удаляются.'))
            record.state = 'cancelled'
            if record.payer_kind == 'platform' and record.fund_id:
                record.message_post(body=_('Задача отменена, резерв возвращён в фонд.'))
        return True

    def action_reset_to_draft(self):
        for record in self:
            if record.state == 'accepted':
                raise UserError(_('Принятую задачу нельзя вернуть в черновик.'))
            record.write({'state': 'draft', 'assignee_id': False,
                          'payment_mode': False, 'submitted_on': False})
        return True

    # ── Действия участника ───────────────────────────────────────────────

    def action_apply(self):
        """Открыть окно заявки: исполнитель выбирает способ оплаты."""
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Заявки принимаются только по опубликованным задачам.'))
        me = self.env.user.partner_id
        if self.application_ids.filtered(lambda a: a.partner_id == me):
            raise UserError(_('Вы уже подали заявку по этой задаче.'))
        methods = self.allowed_method_ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Заявка на задачу «%s»') % self.name,
            'res_model': 'coop.bounty.apply',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_id': self.id,
                'default_method_id': methods.id if len(methods) == 1 else False,
            },
        }

    def action_submit(self):
        """Окно сдачи: ссылка, файлы, что сделано."""
        self.ensure_one()
        if self.state != 'assigned':
            raise UserError(_('Сдать можно только задачу, взятую в работу.'))
        if self.assignee_id != self.env.user.partner_id:
            raise UserError(_('Сдать результат может только исполнитель.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сдать на проверку'),
            'res_model': 'coop.bounty.submit',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    def _coop_do_submit(self, link=False, note=False, attachments=None):
        """Сдача — новой версией; прежние остаются с замечаниями."""
        self.ensure_one()
        if self.state != 'assigned':
            raise UserError(_('Сдать можно только задачу, взятую в работу.'))
        if self.assignee_id != self.env.user.partner_id and not self.env.su:
            raise UserError(_('Сдать результат может только исполнитель.'))
        version = len(self.sudo().submission_ids) + 1
        submission = self.env['coop.bounty.submission'].sudo().create({
            'task_id': self.id,
            'partner_id': self.assignee_id.id,
            'version': version,
            'link': link,
            'note': note,
        })
        if attachments:
            attachments.sudo().write({'res_model': submission._name, 'res_id': submission.id})
            submission.attachment_ids = [(6, 0, attachments.ids)]
        self.sudo().message_post(body=_('Сдана версия %s.') % version)
        # Под sudo: вести задачу исполнитель не вправе, а сдать — да, и
        # проверка выше пускает только его.
        self.sudo().write({'state': 'submitted',
                           'submitted_on': fields.Date.context_today(self)})
        return True

    # ── Спор ─────────────────────────────────────────────────────────────

    def action_open_dispute_decision(self):
        self.ensure_one()
        if not self._coop_is_arbiter():
            raise UserError(_('Спор разбирает администратор платформы.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Решение по спору'),
            'res_model': 'coop.bounty.dispute',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    def action_open_review(self):
        self.ensure_one()
        if not self._coop_my_review_side():
            raise UserError(_('Отзыв по этой задаче вы уже оставили или оставить не можете.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Отзыв по задаче'),
            'res_model': 'coop.bounty.review.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    @api.model
    def _cron_executor_silence(self):
        """Исполнитель молчит после срока (№ 464, как «остановить работу»
        у Gitcoin): на следующий день — напоминание, через семь дней — задача
        снова открыта, резерв остаётся за ней. Зеркало спора по молчанию
        автора: семь дней в обе стороны."""
        today = fields.Date.context_today(self)
        tasks = self.sudo().search([('state', '=', 'assigned'), ('deadline', '<', today)])
        Notification = self.env['coop.notification'].sudo()
        dropped = 0
        for task in tasks:
            if task.deadline + timedelta(days=DISPUTE_AFTER_DAYS) <= today:
                person = task.assignee_id
                task.application_ids.filtered(
                    lambda a: a.partner_id == person and a.state == 'approved').write({'state': 'dropped'})
                task.write({'state': 'published', 'assignee_id': False, 'payment_mode': False,
                            'reminded_on': False, 'assigned_on': False})
                task.message_post(body=_(
                    'Срок прошёл неделю назад, результата нет — исполнитель %s снят, '
                    'задача снова открыта.') % person.display_name)
                Notification._notify(person, _(
                    'Вы сняты с задачи «%s»: срок прошёл неделю назад, результата нет.') % task.name,
                    record=task, kind='other')
                dropped += 1
            elif not task.reminded_on:
                task.write({'reminded_on': today})
                Notification._notify(task.assignee_id, _(
                    'Срок по задаче «%(name)s» прошёл %(date)s. Сдайте результат или напишите '
                    'автору: через неделю после срока задача снова откроется для других.',
                    name=task.name, date=task.deadline.strftime('%d.%m.%Y')),
                    record=task, kind='other')
        return dropped

    @api.model
    def _cron_open_disputes(self):
        """Автор молчит семь дней после сдачи — спор, не автоприёмка."""
        today = fields.Date.context_today(self)
        limit = today - timedelta(days=DISPUTE_AFTER_DAYS)
        tasks = self.sudo().search([('state', '=', 'submitted'),
                                    ('submitted_on', '<=', limit)])
        for task in tasks:
            task.write({'state': 'dispute', 'dispute_on': today})
            task.message_post(body=_(
                'Автор не ответил за %(days)s дней после сдачи — открыт спор. '
                'Его разбирает администратор платформы.', days=DISPUTE_AFTER_DAYS))
        return True


class CoopBountyApplication(models.Model):
    """Заявка участника на выполнение задачи.

    Отдельной записью, а не полем «желающие» у задачи: у заявки есть своё
    состояние, своя дата и свой выбранный способ оплаты, и по отклонённым
    заявкам видно, кому уже отказывали.
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
    method_id = fields.Many2one(
        'coop.bounty.method', string='Выбранный способ',
        help='Один из способов, допустимых автором задачи.')
    message = fields.Text(
        string='Сообщение автору',
        help='Что у вас есть для этой задачи и когда сможете сдать.')
    proposed_deadline = fields.Date(
        string='Сдам до', help='Срок, который называет исполнитель (как у Dework).')
    answer_ids = fields.One2many('coop.bounty.answer', 'application_id', string='Ответы на вопросы')
    state = fields.Selection([
        ('applied', 'Подана'),
        ('approved', 'Утверждена'),
        ('rejected', 'Отклонена'),
        ('dropped', 'Снят: срок прошёл'),
    ], string='Состояние', default='applied', required=True, index=True)

    _one_per_task = models.Constraint(
        'unique(task_id, partner_id)',
        'Участник уже подал заявку по этой задаче.',
    )

    def _coop_check_author(self):
        """Утверждает и отклоняет тот, кто вправе вести задачу."""
        for record in self:
            record.task_id.check_access('write')

    def action_approve(self):
        """Утвердить исполнителя.

        Остальные заявки по задаче отклоняются автоматически: исполнитель
        один, и оставлять чужие заявки в состоянии «подана» значит держать
        людей в неведении. Выбранный в заявке способ закрепляется за
        задачей.
        """
        self._coop_check_author()
        for record in self.sudo():
            if record.task_id.state not in ('published', 'assigned'):
                raise UserError(_(
                    'Утвердить исполнителя можно только по опубликованной задаче.'))
            others = record.task_id.application_ids - record
            others.filtered(lambda a: a.state == 'applied').write({'state': 'rejected'})
            record.state = 'approved'
            method = record.method_id or record.task_id.allowed_method_ids[:1]
            record.task_id.write({
                'assignee_id': record.partner_id.id,
                'state': 'assigned',
                'payment_mode': method.code or False,
                'assigned_on': fields.Date.context_today(record),
                'reminded_on': False,
            })
            record.task_id.message_post(body=_(
                'Исполнителем утверждён %(who)s, способ оплаты — %(method)s.',
                who=record.partner_id.display_name, method=method.name or '—'))
        return True

    def action_reject(self):
        self._coop_check_author()
        for record in self.sudo():
            record.state = 'rejected'
            if record.task_id.assignee_id == record.partner_id:
                record.task_id.write({'assignee_id': False, 'state': 'published',
                                      'payment_mode': False})
        return True

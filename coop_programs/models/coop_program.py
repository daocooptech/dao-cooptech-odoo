# -*- coding: utf-8 -*-
"""Целевые программы кооперации.

Программа — не проект и не сделка. Проект делают ради результата,
сделку — ради обмена; программу заводят, чтобы несколько самостоятельных
хозяйств делали сообща то, что поодиночке невыгодно: закупали оптом,
делили технику, держали общий склад. Хозяйство при этом остаётся своим —
в этом отличие от слияния, и участник должен видеть его сразу.

У программы есть основа: работа, из которой взята механика. Ссылка на
первоисточник стоит в карточке не для солидности — предлагаемое
устройство должно быть проверенным, а не придуманным на ходу, и это
проверяемо по ссылке.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopProgram(models.Model):
    _name = 'coop.program'
    _description = 'Целевая программа кооперации'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Название', required=True, tracking=True)
    active = fields.Boolean(default=True)

    organizer_id = fields.Many2one(
        'res.partner', string='Организующий кооператив', required=True,
        index=True, tracking=True,
        help='Тот, кто ведёт программу и отвечает за общий фонд.')
    city = fields.Char(string='Город', index=True)
    geography = fields.Char(
        string='География',
        help='«Москва, участие удалённо по всей РФ» — когда программа не '
             'привязана к одному городу.')

    industry = fields.Selection([
        ('agriculture', 'Сельское хозяйство'),
        ('it', 'ИТ и цифровая экономика'),
        ('housing', 'Жильё и строительство'),
        ('craft', 'Ремёсла и производство'),
        ('trade', 'Снабжение и сбыт'),
        ('education', 'Образование'),
        ('energy', 'Энергетика'),
        ('other', 'Прочее'),
    ], string='Направление', default='other', required=True, index=True)

    fund_amount = fields.Monetary(
        string='Фонд программы', currency_field='currency_id', tracking=True,
        help='Сколько собрано на общие закупки и работы.')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    duration_months = fields.Integer(string='Срок, месяцев', default=12)

    description = fields.Html(string='О программе')

    # ── Первоисточник ────────────────────────────────────────────────────
    #
    # Три поля, а не одна строка: по автору ищут, по году отличают
    # издания, а суть нужна тому, кто не будет читать первоисточник
    # целиком — а таких большинство.
    source_author = fields.Char(string='Автор')
    source_title = fields.Char(string='Работа')
    source_year = fields.Char(string='Годы')
    source_summary = fields.Text(
        string='Что взято',
        help='В одном абзаце: какая именно механика взята из работы.')

    state = fields.Selection([
        ('draft', 'Готовится'),
        ('collecting', 'Набор участников'),
        ('active', 'Идёт'),
        ('finished', 'Завершена'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    participant_ids = fields.Many2many(
        'res.partner', 'coop_program_participant_rel', 'program_id',
        'partner_id', string='Участники')
    participant_count = fields.Integer(
        string='Участников', compute='_compute_participant_count', store=True)
    subscriber_ids = fields.Many2many(
        'res.partner', 'coop_program_subscriber_rel', 'program_id',
        'partner_id', string='Подписаны на новости',
        help='Следят за лентой, но в программу не вступили: интерес есть, '
             'обязательств пока нет.')

    step_ids = fields.One2many(
        'coop.program.step', 'program_id', string='Механика программы')
    need_ids = fields.One2many(
        'coop.program.need', 'program_id', string='Потребности')
    resource_ids = fields.Many2many(
        'coop.resource', string='Ресурсы программы')

    is_participant = fields.Boolean(
        string='Я участвую', compute='_compute_my_state',
        search='_search_is_participant')
    is_subscribed = fields.Boolean(
        string='Я подписан', compute='_compute_my_state')

    _fund_positive = models.Constraint(
        'check(fund_amount >= 0)',
        'Фонд программы не может быть отрицательным.',
    )

    @api.depends('participant_ids')
    def _compute_participant_count(self):
        for record in self:
            record.participant_count = len(record.participant_ids)

    @api.depends_context('uid')
    @api.depends('participant_ids', 'subscriber_ids')
    def _compute_my_state(self):
        me = self.env.user._coop_acting_partner()
        for record in self:
            record.is_participant = me in record.participant_ids
            record.is_subscribed = me in record.subscriber_ids

    def _search_is_participant(self, operator, value):
        # Odoo приводит «= True» к «in {True}» и передаёт свой набор.
        if isinstance(value, bool):
            wanted = value
        else:
            items = list(value)
            if len(items) != 1 or not isinstance(items[0], bool):
                raise ValueError(_('Поддерживается только «да» или «нет».'))
            wanted = items[0]
        if operator in ('=', 'in'):
            positive = wanted
        elif operator in ('!=', 'not in'):
            positive = not wanted
        else:
            raise ValueError(_('Поддерживается только «да» или «нет».'))
        me = self.env.user._coop_acting_partner()
        return [('participant_ids', 'in' if positive else 'not in', me.ids)]

    # ── Действия участника ───────────────────────────────────────────────

    def action_join(self):
        """Присоединиться к программе.

        Вступление в сам кооператив — отдельное действие: программа может
        принимать и тех, кто пайщиком становиться не готов. Смешивать их
        нельзя, иначе человек, нажавший «присоединиться», обнаружит себя
        пайщиком с паевым взносом.
        """
        me = self.env.user._coop_acting_partner()
        for record in self:
            if record.state == 'finished':
                raise UserError(_(
                    'Программа завершена — присоединяться уже не к чему.'))
            if me in record.participant_ids:
                raise UserError(_('Вы уже участвуете в этой программе.'))
            record.participant_ids = [(4, me.id)]
            record.message_post(body=_(
                '%(name)s присоединился к программе.', name=me.display_name))
        return True

    def action_leave(self):
        """Выйти из программы."""
        me = self.env.user._coop_acting_partner()
        for record in self:
            record.participant_ids = [(3, me.id)]
        return True

    def action_subscribe(self):
        """Подписаться на новости, не вступая."""
        me = self.env.user._coop_acting_partner()
        for record in self:
            if me not in record.subscriber_ids:
                record.subscriber_ids = [(4, me.id)]
            record.message_subscribe(partner_ids=me.ids)
        return True

    def action_unsubscribe(self):
        me = self.env.user._coop_acting_partner()
        for record in self:
            record.subscriber_ids = [(3, me.id)]
            record.message_unsubscribe(partner_ids=me.ids)
        return True


class CoopProgramStep(models.Model):
    """Механика программы: из чего она состоит.

    Не задачи и не этапы — именно устройство: что делается сообща.
    Порядок важен, потому что по нему участник понимает, во что
    ввязывается, ещё до вступления.
    """
    _name = 'coop.program.step'
    _description = 'Механика целевой программы'
    _order = 'sequence, id'

    program_id = fields.Many2one(
        'coop.program', string='Программа', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Что делается сообща', required=True)
    icon = fields.Char(
        string='Значок',
        help='Один символ рядом с описанием — как в макете: 📦, 🌾, 🏬.')
    note = fields.Text(string='Пояснение')


class CoopProgramNeed(models.Model):
    """Потребность программы: чего не хватает.

    Открытая потребность — это приглашение, а не жалоба: участник видит,
    чем может помочь прямо сейчас, и по какой части.
    """
    _name = 'coop.program.need'
    _description = 'Потребность целевой программы'
    _order = 'state, sequence, id'

    program_id = fields.Many2one(
        'coop.program', string='Программа', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Что нужно', required=True)
    kind = fields.Selection([
        ('people', 'Люди'),
        ('equipment', 'Техника'),
        ('money', 'Деньги'),
        ('materials', 'Материалы'),
        ('knowledge', 'Знания'),
    ], string='Чего именно', default='people', required=True)
    amount = fields.Monetary(
        string='Оценка', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', related='program_id.currency_id', store=True)
    state = fields.Selection([
        ('open', 'Открыта'),
        ('covered', 'Закрыта'),
    ], string='Состояние', default='open', required=True, index=True)
    covered_by_id = fields.Many2one(
        'res.partner', string='Кто закрыл', readonly=True)

    def action_cover(self):
        """Закрыть потребность собой.

        Отдельного согласования нет намеренно: потребность закрывает тот,
        кто берётся, а разбирается с этим организатор программы — как в
        жизни, где на «нужен агроном» отзывается агроном, а не заявка.
        """
        me = self.env.user._coop_acting_partner()
        for record in self:
            if record.state == 'covered':
                raise UserError(_('Эту потребность уже закрыли.'))
            record.write({'state': 'covered', 'covered_by_id': me.id})
            record.program_id.message_post(body=_(
                '%(who)s закрывает потребность «%(what)s».',
                who=me.display_name, what=record.name))
        return True

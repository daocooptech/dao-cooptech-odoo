# -*- coding: utf-8 -*-
"""События: где кооперация происходит лично.

Всё остальное на платформе — записи об уговорах. Событие единственное,
что случается вживую, и от него зависит, состоится ли остальное:
собрание пайщиков утверждает бюджет, ярмарка сводит продавца с
покупателем, созвон разбирает чужой код.

Запись на событие — обязательство перед организатором. Он считает места,
еду и стулья, поэтому отмена видна и учитывается, а не проходит молча:
«записалось шестьдесят четыре, пришло двадцать» — это не мелочь, а
испорченная ярмарка.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopEvent(models.Model):
    _name = 'coop.event'
    _description = 'Событие кооперативной жизни'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    name = fields.Char(string='Название', required=True, tracking=True)
    active = fields.Boolean(default=True)
    icon = fields.Char(
        string='Значок', default='📅',
        help='Один символ в карточке: 🗳️ собрание, 📚 обучение, 🎉 ярмарка.')

    category = fields.Selection([
        ('meeting', 'Собрания пайщиков'),
        ('learning', 'Обучение'),
        ('fair', 'Праздники и ярмарки'),
        ('community', 'Мероприятия сообществ'),
        ('meetup', 'Встречи и знакомства'),
    ], string='Вид', default='meetup', required=True, index=True, tracking=True)

    format = fields.Selection([
        ('offline', 'Офлайн'),
        ('online', 'Онлайн'),
        ('mixed', 'Смешанный'),
    ], string='Формат', default='offline', required=True, index=True)

    organizer_id = fields.Many2one(
        'res.partner', string='Организатор', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True)
    community_id = fields.Many2one(
        'coop.community', string='Сообщество',
        help='Если событие проводит сообщество, а не отдельный участник.')

    city = fields.Char(string='Город', index=True)
    place = fields.Char(
        string='Место',
        help='Адрес или ссылка на созвон — смотря какой формат.')

    date_start = fields.Datetime(string='Начало', required=True, index=True,
                                 tracking=True)
    date_end = fields.Datetime(string='Окончание')

    description = fields.Html(string='Описание')

    capacity = fields.Integer(
        string='Мест',
        help='Ноль — без ограничения. Иначе запись закрывается, когда мест '
             'не остаётся.')
    signup_ids = fields.One2many(
        'coop.event.signup', 'event_id', string='Записи')
    signup_count = fields.Integer(
        string='Записались', compute='_compute_signups', store=True)
    seats_left = fields.Integer(
        string='Свободных мест', compute='_compute_signups', store=True)

    state = fields.Selection([
        ('draft', 'Готовится'),
        ('open', 'Идёт запись'),
        ('closed', 'Запись закрыта'),
        ('held', 'Состоялось'),
        ('cancelled', 'Отменено'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    is_past = fields.Boolean(string='Прошло', compute='_compute_is_past',
                             search='_search_is_past')
    am_i_signed = fields.Boolean(
        string='Я записан', compute='_compute_am_i_signed',
        search='_search_am_i_signed')

    signup_label = fields.Char(
        string='Сколько людей', compute='_compute_signup_label',
        help='Готовая строка для карточки: у будущего события люди '
             'записались, у прошедшего — участвовали. Считается здесь, '
             'а не в шаблоне: склонение числительного шаблону не по силам.')

    @api.depends('signup_ids.state', 'capacity')
    def _compute_signups(self):
        for record in self:
            going = record.signup_ids.filtered(lambda s: s.state == 'going')
            record.signup_count = len(going)
            record.seats_left = (record.capacity - len(going)
                                 if record.capacity else 0)

    @api.depends('signup_count', 'is_past')
    def _compute_signup_label(self):
        for record in self:
            n = record.signup_count or 0
            tail, hundred = n % 10, n % 100
            if record.is_past:
                if hundred in (11, 12, 13, 14):
                    word = 'участников'
                elif tail == 1:
                    word = 'участник'
                elif tail in (2, 3, 4):
                    word = 'участника'
                else:
                    word = 'участников'
            else:
                word = ('записался' if tail == 1 and hundred != 11
                        else 'записались')
            record.signup_label = '%d %s' % (n, word)

    @api.depends('date_start')
    def _compute_is_past(self):
        now = fields.Datetime.now()
        for record in self:
            record.is_past = bool(record.date_start and record.date_start < now)

    def _search_is_past(self, operator, value):
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
        now = fields.Datetime.now()
        return [('date_start', '<' if positive else '>=', now)]

    @api.depends_context('uid')
    @api.depends('signup_ids.partner_id', 'signup_ids.state')
    def _compute_am_i_signed(self):
        me = self.env.user._coop_acting_partner()
        for record in self:
            record.am_i_signed = bool(record.signup_ids.filtered(
                lambda s: s.partner_id == me and s.state == 'going'))

    def _search_am_i_signed(self, operator, value):
        """Отбор «я записан» — на стороне сервера.

        Вычисляемое поле без метода поиска в домен ставить нельзя: Odoo
        отвергает такой вид целиком при загрузке, и раздел не ставится
        вовсе.
        """
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
        signed = self.env['coop.event.signup'].search([
            ('partner_id', '=', me.id), ('state', '=', 'going')])
        return [('id', 'in' if positive else 'not in', signed.mapped('event_id').ids)]

    # ── Запись ───────────────────────────────────────────────────────────

    def action_signup(self):
        """Записаться на событие."""
        me = self.env.user._coop_acting_partner()
        Signup = self.env['coop.event.signup']
        for record in self:
            if record.state in ('closed', 'held', 'cancelled'):
                raise UserError(_(
                    'Запись на это событие закрыта.'))
            if record.capacity and record.seats_left <= 0:
                raise UserError(_(
                    'Мест не осталось. Организатор считает места заранее — '
                    'прийти «просто так» значит занять чужое.'))
            existing = record.signup_ids.filtered(
                lambda s: s.partner_id == me)
            if existing:
                existing.write({'state': 'going'})
            else:
                Signup.create({'event_id': record.id, 'partner_id': me.id})
            record.message_subscribe(partner_ids=me.ids)
        return True

    def action_cancel_signup(self):
        """Отменить запись.

        Отмена остаётся записью, а не удаляется: организатор должен
        видеть, сколько человек передумало — по этому он поймёт, стоит
        ли в следующий раз рассчитывать на заявленное число.
        """
        me = self.env.user._coop_acting_partner()
        for record in self:
            mine = record.signup_ids.filtered(lambda s: s.partner_id == me)
            mine.write({'state': 'cancelled'})
        return True

    def action_open(self):
        self.write({'state': 'open'})
        return True

    def action_close(self):
        self.write({'state': 'closed'})
        return True

    def action_hold(self):
        """Отметить, что событие состоялось."""
        self.write({'state': 'held'})
        return True

    def action_cancel(self):
        """Отменить событие — записавшиеся узнают из ленты."""
        for record in self:
            record.write({'state': 'cancelled'})
            record.message_post(body=_(
                'Событие отменено. Записавшимся приходить не нужно.'))
        return True


class CoopEventSignup(models.Model):
    """Запись на событие."""
    _name = 'coop.event.signup'
    _description = 'Запись на событие'
    _order = 'create_date desc, id desc'

    event_id = fields.Many2one(
        'coop.event', string='Событие', required=True, ondelete='cascade',
        index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True)
    state = fields.Selection([
        ('going', 'Придёт'),
        ('cancelled', 'Отменил'),
        ('attended', 'Был'),
        ('missed', 'Не пришёл'),
    ], string='Состояние', default='going', required=True, index=True)
    note = fields.Char(string='Примечание')

    _unique_signup = models.Constraint(
        'unique(event_id, partner_id)',
        'Участник уже записан на это событие.',
    )

    def action_attended(self):
        """Отметить, что человек был.

        Отметку ставит организатор после события. Она нужна не для
        учёта ради учёта: по ней видно, на кого можно рассчитывать, а
        кто записывается и не приходит.
        """
        self.write({'state': 'attended'})
        return True

    def action_missed(self):
        self.write({'state': 'missed'})
        return True

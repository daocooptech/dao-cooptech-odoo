# -*- coding: utf-8 -*-
"""Аукционы: торг там, где цена неизвестна заранее.

Два вида, и они противоположны по смыслу.

**На повышение.** Кооператив продаёт излишки — урожай, технику,
помещение в аренду. Цена растёт, побеждает тот, кто предложил больше.

**Редукцион.** Кооператив ищет подрядчика или поставщика. Цена падает,
побеждает тот, кто взялся дешевле. Стартовая цена здесь — потолок, выше
которого предложения не принимаются.

Общее у них одно правило, ради которого аукцион и заводят вместо
объявления: ставка в последние минуты продлевает торг. Без продления
выигрывает не тот, кто больше готов заплатить, а тот, у кого лучше связь
и быстрее рука — а это не то, что кооператив хочет поощрять.
"""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopAuction(models.Model):
    _name = 'coop.auction'
    _description = 'Аукцион'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end, id desc'

    name = fields.Char(string='Лот', required=True, tracking=True)
    active = fields.Boolean(default=True)

    kind = fields.Selection([
        ('direct', 'На повышение'),
        ('reverse', 'Редукцион'),
    ], string='Вид торга', default='direct', required=True, index=True,
        tracking=True,
        help='На повышение — продаём, побеждает больший. Редукцион — ищем '
             'исполнителя, побеждает меньший.')

    owner_id = fields.Many2one(
        'res.partner', string='Организатор', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(), tracking=True)
    resource_id = fields.Many2one(
        'coop.resource', string='Объявление',
        help='Если лот уже описан объявлением в каталоге ресурсов.')
    # Фотография лота — своя. Сначала предполагалось брать её у ресурса,
    # выставленного на торги, но связь оказалась пустой у всех ста пяти
    # аукционов: лоты здесь свои — прицеп после ремонта, вывоз зерна,
    # ремонт кровли, — и в каталоге ресурсов таких записей нет. Поэтому
    # снимок хранится у самого аукциона; когда лот всё же ссылается на
    # ресурс, поле заполняется его фотографией.
    image_512 = fields.Image(string='Фото лота', max_width=512, max_height=512)

    city = fields.Char(string='Город', index=True)
    description = fields.Html(string='Описание лота')

    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    start_price = fields.Monetary(
        string='Стартовая цена', required=True, currency_field='currency_id',
        help='На повышение — с чего начинаем. В редукционе — потолок, выше '
             'которого предложения не принимаются.')
    step = fields.Monetary(
        string='Шаг', required=True, currency_field='currency_id', default=100,
        help='Меньше шага ставку не принимаем: иначе торг превращается в '
             'соревнование по добавлению рубля.')
    reserve_price = fields.Monetary(
        string='Резервная цена', currency_field='currency_id',
        help='Ниже этой цены продавать не готовы. Ноль — резерва нет. '
             'Участникам не показывается — иначе она становится ценой.')

    date_start = fields.Datetime(
        string='Начало', required=True, default=fields.Datetime.now)
    date_end = fields.Datetime(string='Окончание', required=True, index=True,
                               tracking=True)
    extend_minutes = fields.Integer(
        string='Продление, мин', default=10,
        help='Ставка в последние минуты продлевает торг на столько же. '
             'Ноль — без продления.')

    bid_ids = fields.One2many('coop.auction.bid', 'auction_id', string='Ставки')
    bid_count = fields.Integer(string='Ставок', compute='_compute_bids',
                               store=True)
    current_price = fields.Monetary(
        string='Текущая цена', compute='_compute_bids', store=True,
        currency_field='currency_id')
    leader_id = fields.Many2one(
        'res.partner', string='Лидер', compute='_compute_bids', store=True)
    winner_id = fields.Many2one(
        'res.partner', string='Победитель', readonly=True, copy=False)

    state = fields.Selection([
        ('draft', 'Готовится'),
        ('running', 'Идут торги'),
        ('finished', 'Завершён'),
        ('no_bids', 'Без ставок'),
        ('cancelled', 'Отменён'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    my_bid = fields.Monetary(
        string='Моя ставка', compute='_compute_my_bid',
        currency_field='currency_id')
    minutes_left = fields.Integer(
        string='Осталось минут', compute='_compute_minutes_left')
    can_bid = fields.Boolean(
        string='Можно поставить', compute='_compute_can_bid',
        help='Торг идёт, срок не вышел, и ставящий — не организатор и не '
             'нынешний лидер.')
    coop_can_edit = fields.Boolean(
        string='Условия торга можно править', compute='_compute_coop_can_edit',
        help='Правит только организатор и только пока торг готовится: '
             'после открытия условия неизменны — на них уже поставили.')
    live_rank = fields.Integer(
        string='Порядок на витрине', compute='_compute_live_rank',
        store=True, index=True,
        help='Идущие торги впереди завершённых. Число, а не сортировка по '
             'состоянию: по алфавиту «завершён» встаёт раньше «идут торги».')

    _step_positive = models.Constraint(
        'check(step > 0)',
        'Шаг должен быть больше нуля.',
    )
    _start_price_positive = models.Constraint(
        'check(start_price > 0)',
        'Стартовая цена должна быть больше нуля.',
    )

    @api.depends('bid_ids.amount', 'kind', 'start_price')
    def _compute_bids(self):
        for record in self:
            bids = record.bid_ids
            record.bid_count = len(bids)
            if not bids:
                record.current_price = record.start_price
                record.leader_id = False
                continue
            best = (max(bids, key=lambda b: b.amount) if record.kind == 'direct'
                    else min(bids, key=lambda b: b.amount))
            record.current_price = best.amount
            record.leader_id = best.partner_id

    @api.depends_context('uid')
    @api.depends('bid_ids.amount', 'bid_ids.partner_id')
    def _compute_my_bid(self):
        me = self.env.user._coop_acting_partner()
        for record in self:
            mine = record.bid_ids.filtered(lambda b: b.partner_id == me)
            record.my_bid = (max(mine.mapped('amount'))
                             if record.kind == 'direct' and mine
                             else min(mine.mapped('amount')) if mine else 0.0)

    @api.depends('date_end')
    def _compute_minutes_left(self):
        now = fields.Datetime.now()
        for record in self:
            if not record.date_end or record.date_end < now:
                record.minutes_left = 0
            else:
                record.minutes_left = int(
                    (record.date_end - now).total_seconds() // 60)

    @api.depends('state')
    def _compute_live_rank(self):
        """Витрина торгов показывает то, где ещё можно поучаствовать.

        До этого каталог сортировался по дате окончания, и первыми шли
        торги, закончившиеся раньше всех: из ста пяти лотов на витрине
        стояли одни завершённые, а все семь идущих не попадали на экран
        вовсе. Раздел, где нельзя сделать ставку, — не торги, а архив.
        """
        порядок = {
            'running': 0,     # идут — ради них сюда и заходят
            'draft': 1,       # вот-вот начнутся
            'no_bids': 2,     # закончились, но лот свободен
            'finished': 3,
            'cancelled': 4,
        }
        for record in self:
            record.live_rank = порядок.get(record.state, 9)

    @api.depends_context('uid')
    @api.depends('state', 'owner_id')
    def _compute_coop_can_edit(self):
        """Кому и когда можно править условия торга.

        Права на запись уже описаны правилом видимости: писать в аукцион
        может тот, от чьего имени он размещён. Но правило срабатывает
        только при сохранении — до этого форма даёт править всё подряд, и
        человек узнаёт об отказе, уже потеряв набранное. Владелец
        16 сентября 2026: «ты даешь возможность править поля, а потом при
        сохранении выводишь ошибку, надо сделать так что править было не
        возможно».

        Второе условие — состояние. Условия торга неизменны с момента
        открытия: стартовая цена, шаг и срок — то, на что ставили. Менять
        их задним числом значит переписывать правила игры после ставок.
        """
        publishers = self.env.user.coop_publisher_partner_ids
        for record in self:
            record.coop_can_edit = (
                record.state == 'draft' and record.owner_id in publishers)

    @api.depends('state', 'date_end', 'owner_id', 'leader_id')
    def _compute_can_bid(self):
        """Условия участия одним признаком — тем же, что и у проверки.

        Кнопку показывает он, отказ выдаёт `_check_can_bid`. Разойдись
        они — и человек увидел бы кнопку, которая отвечает ошибкой; в
        вакансиях это ровно так и вышло 15 сентября 2026.
        """
        me = self.env.user._coop_acting_partner()
        now = fields.Datetime.now()
        for record in self:
            record.can_bid = bool(
                record.state == 'running'
                and record.date_end and record.date_end > now
                and record.owner_id != me
                and record.leader_id != me)

    # ── Торг ─────────────────────────────────────────────────────────────

    def action_start(self):
        for record in self:
            if record.date_end <= fields.Datetime.now():
                raise UserError(_(
                    'Окончание торга уже прошло — начинать нечего.'))
            record.write({'state': 'running'})
            record.message_post(body=_('Торги открыты.'))
        return True

    def action_bid(self, amount=None):
        """Открыть окно ставки — или поставить, если сумма уже известна.

        Кнопки у этого действия не было вовсе: метод в модели написан, а
        нажать его негде, и участник мог только смотреть за торгом.
        Сумму надо где-то ввести, а править саму запись аукциона
        участнику нельзя — отсюда окно.

        Сигнатура прежняя: с суммой метод работает как раньше, и вызовы
        из кода ничего не замечают.
        """
        self.ensure_one()
        if amount is None:
            self._check_can_bid()
            return {
                'type': 'ir.actions.act_window',
                'name': _('Ставка на «%s»') % self.name,
                'res_model': 'coop.auction.bid.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_auction_id': self.id},
            }
        return self._do_bid(amount)

    def _check_can_bid(self):
        """Условия участия — до окна, а не после ввода суммы."""
        self.ensure_one()
        me = self.env.user._coop_acting_partner()
        if self.state != 'running':
            raise UserError(_('Торги по этому лоту не идут.'))
        if self.date_end <= fields.Datetime.now():
            raise UserError(_('Время торга вышло.'))
        if self.owner_id == me:
            raise UserError(_(
                'Организатор не участвует в своём торге: это разгон цены, '
                'а не участие.'))
        if self.leader_id == me:
            raise UserError(_(
                'Вы и так лидируете. Перебивать самого себя незачем.'))

    def _suggested_bid(self):
        """Ближайшая допустимая ставка — её и подставляем в окно."""
        self.ensure_one()
        if self.kind == 'direct':
            return (self.current_price + self.step if self.bid_ids
                    else self.start_price)
        return (self.current_price - self.step if self.bid_ids
                else self.start_price)

    def _do_bid(self, amount=None):
        """Сделать ставку.

        Проверок три, и каждая закрывает свой способ испортить торг:
        нельзя ставить вне торга, нельзя перебивать самого себя, нельзя
        двигать цену меньше чем на шаг.
        """
        self.ensure_one()
        me = self.env.user._coop_acting_partner()
        now = fields.Datetime.now()

        if self.state != 'running':
            raise UserError(_('Торги по этому лоту не идут.'))
        if self.date_end <= now:
            raise UserError(_('Время торга вышло.'))
        if self.owner_id == me:
            raise UserError(_(
                'Организатор не участвует в своём торге: это разгон цены, '
                'а не участие.'))
        if self.leader_id == me:
            raise UserError(_(
                'Вы и так лидируете. Перебивать самого себя незачем.'))

        amount = float(amount or 0.0)
        if self.kind == 'direct':
            minimum = (self.current_price + self.step if self.bid_ids
                       else self.start_price)
            if amount < minimum:
                raise UserError(_(
                    'Ставка должна быть не меньше %(min)s: шаг торга '
                    '%(step)s.', min=minimum, step=self.step))
        else:
            maximum = (self.current_price - self.step if self.bid_ids
                       else self.start_price)
            if amount > maximum:
                raise UserError(_(
                    'В редукционе предложение должно быть не больше '
                    '%(max)s: шаг торга %(step)s.',
                    max=maximum, step=self.step))
            if amount <= 0:
                raise UserError(_('Предложение должно быть больше нуля.'))

        # Прежнего лидера запоминаем до ставки: после неё поле уже
        # пересчитано, и известить вытесненного будет некого.
        прежний = self.leader_id

        bid = self.env['coop.auction.bid'].create({
            'auction_id': self.id,
            'partner_id': me.id,
            'amount': amount,
        })

        # Не зная, что его перебили, участник не поднимет ставку — и торг
        # выигрывает не тот, кто больше готов заплатить, а тот, кто
        # случайно заглянул на страницу последним.
        if прежний:
            self.env['coop.notification']._notify(
                прежний,
                _('Вашу ставку на «%(лот)s» перебили: теперь %(цена)s.',
                  лот=self.name, цена=amount),
                record=self, kind='auction')

        # Антиснайпинг: ставка на последних минутах отодвигает конец.
        #
        # Через sudo: продление срока и запись в ленту — последствия уже
        # принятой ставки, а не правка торга участником. Торг чужой, и
        # права двигать его окончание у того, кто ставит, нет и быть не
        # должно — иначе ставку можно было бы использовать как способ
        # переписать чужой лот.
        if self.extend_minutes:
            edge = self.date_end - timedelta(minutes=self.extend_minutes)
            if now >= edge:
                продлённый = self.date_end + timedelta(
                    minutes=self.extend_minutes)
                self.sudo().date_end = продлённый
                self.sudo().message_post(body=_(
                    'Ставка на последних минутах — торг продлён до %(until)s.',
                    until=fields.Datetime.to_string(продлённый)))
        return bid

    def action_finish(self):
        """Подвести итог торга.

        Резервная цена решает, состоялась ли продажа: если лучшее
        предложение её не достигло, лот не продан. Показывать резерв
        участникам нельзя — он тут же станет ценой, ниже которой никто не
        поставит.
        """
        for record in self:
            if not record.bid_ids:
                record.write({'state': 'no_bids'})
                record.message_post(body=_('Торг закончился без ставок.'))
                continue
            best = record.current_price
            reserve_ok = (not record.reserve_price
                          or (best >= record.reserve_price
                              if record.kind == 'direct'
                              else best <= record.reserve_price))
            if not reserve_ok:
                record.write({'state': 'no_bids'})
                record.message_post(body=_(
                    'Лучшее предложение — %(best)s, резервная цена не '
                    'достигнута. Лот не продан.', best=best))
                continue
            record.write({'state': 'finished', 'winner_id': record.leader_id.id})
            record.message_post(body=_(
                'Торг завершён: %(who)s, %(price)s.',
                who=record.leader_id.display_name, price=best))
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    @api.model
    def _cron_close_expired(self):
        """Закрыть торги, у которых вышло время.

        Отдельным заданием, а не «по факту открытия страницы»: иначе
        аукцион закрывается тогда, когда на него кто-то зашёл, и время
        окончания перестаёт что-либо значить.
        """
        expired = self.search([
            ('state', '=', 'running'),
            ('date_end', '<=', fields.Datetime.now()),
        ])
        expired.action_finish()
        return len(expired)


class CoopAuctionBid(models.Model):
    """Ставка в торге.

    Ставки не редактируются и не удаляются: история торга — то, чем он
    доказуем. Ошибся в сумме — перебивай следующей ставкой, как на любом
    настоящем аукционе.
    """
    _name = 'coop.auction.bid'
    _description = 'Ставка в аукционе'
    _order = 'create_date desc, id desc'

    auction_id = fields.Many2one(
        'coop.auction', string='Аукцион', required=True, ondelete='cascade',
        index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Участник', required=True, index=True)
    amount = fields.Monetary(
        string='Сумма', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', related='auction_id.currency_id', store=True)

    def write(self, values):
        raise UserError(_(
            'Ставку нельзя изменить: история торга — то, чем он доказуем. '
            'Ошиблись в сумме — перебейте следующей ставкой.'))

    def unlink(self):
        raise UserError(_(
            'Ставку нельзя удалить: без полной истории торг не доказать.'))

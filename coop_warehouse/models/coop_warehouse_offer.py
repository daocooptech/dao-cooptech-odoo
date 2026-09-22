# -*- coding: utf-8 -*-
"""Биржа складских мощностей: у кого место простаивает, кому его не хватает.

У биржи две стороны, и они не зеркальны. «Предлагают мощности» — это
всегда конкретный склад с адресом, ёмкостью и температурой. «Ищут
мощности» — потребность, у которой склада ещё нет: нужен морозильник на
три месяца, где угодно в пределах города. Поэтому у предложения склад
обязателен, а у запроса его нет вовсе, и оба живут в одной модели:
участник ходит по бирже одним списком, а не по двум разным экранам.

Условие передачи — не одно. Один и тот же угол склада хозяин готов
сдать за деньги, отдать под ответственное хранение или взять долей в
проекте, и выбирает откликающийся, а не он. Отсюда строки условий:
у объявления их несколько, с ценой у денежных и без цены у обменных.
Главная цена на плитке — самая дешёвая из денежных; если денежных нет,
плитка честно говорит «без денег».
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coop_warehouse import (CAPACITY_UNITS, STORAGE_KINDS, TERM_KINDS,
                             amount_with_unit)

SIDES = [
    ('offer', 'Предлагают мощности'),
    ('request', 'Ищут мощности'),
]

# Условия, за которые платят деньгами. Остальные три — это вклад,
# обмен и доля, и цены у них нет по смыслу, а не по недосмотру.
MONEY_TERMS = ('rent', 'custody', 'buyout')

KIND_ICONS = {
    'dry_heated': '🏬',
    'dry_cold': '🏚',
    'chilled': '🧊',
    'frozen': '❄',
    'open': '🏗',
}


class CoopWarehouseOffer(models.Model):
    _name = 'coop.warehouse.offer'
    _description = 'Объявление на бирже мощностей'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'coop.page.mixin']
    _order = 'published_on desc, id desc'

    name = fields.Char(string='Заголовок', required=True, tracking=True)
    side = fields.Selection(
        SIDES, string='Сторона', required=True, default='offer', index=True,
        tracking=True)

    owner_id = fields.Many2one(
        'res.partner', string='Кто разместил', required=True, index=True,
        default=lambda self: self.env.user._coop_acting_partner(),
        tracking=True)
    warehouse_id = fields.Many2one(
        'coop.warehouse', string='Склад', index=True, ondelete='cascade',
        help='У предложения обязателен: место без адреса и температуры '
             'никому не годится. У запроса пуст — склада ещё нет.')

    city = fields.Char(string='Город', index=True)
    storage_kind = fields.Selection(
        STORAGE_KINDS, string='Тип хранения', index=True, tracking=True)
    icon = fields.Char(string='Значок', compute='_compute_icon')
    side_short = fields.Char(string='Сторона коротко',
                             compute='_compute_icon')

    volume = fields.Float(string='Объём', digits=(12, 1), required=True)
    capacity_unit = fields.Selection(
        CAPACITY_UNITS, string='Единица', default='sqm', required=True)
    volume_label = fields.Char(string='Сколько', compute='_compute_labels',
                               store=True)

    date_from = fields.Date(string='С какого числа')
    date_to = fields.Date(string='По какое')
    period_label = fields.Char(string='Срок', compute='_compute_labels',
                               store=True)

    term_ids = fields.One2many(
        'coop.warehouse.offer.term', 'offer_id', string='Условия')
    terms_label = fields.Char(string='Условия', compute='_compute_labels',
                              store=True)
    currency_id = fields.Many2one(
        'res.currency', string='Валюта',
        default=lambda self: self.env.company.currency_id)
    main_price = fields.Monetary(
        string='Главная цена', currency_field='currency_id',
        compute='_compute_labels', store=True,
        help='Самое дешёвое из денежных условий. Ноль — значит денежных '
             'условий нет вовсе.')
    main_price_label = fields.Char(
        string='Цена', compute='_compute_labels', store=True)

    state = fields.Selection([
        ('draft', 'Черновик'),
        ('published', 'Опубликовано'),
        ('matched', 'Договорились'),
        ('closed', 'Снято'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)
    published_on = fields.Date(string='Опубликовано', index=True)

    description = fields.Html(string='Описание')
    contact_note = fields.Char(
        string='Как связаться',
        help='Что писать в отклике: время приёмки, пандус, допуск машин.')

    deal_ids = fields.One2many(
        'coop.deal', 'warehouse_offer_id', string='Сделки по объявлению')
    deal_count = fields.Integer(string='Сделок', compute='_compute_deal_count')

    is_mine = fields.Boolean(
        string='Моё объявление', compute='_compute_is_mine',
        search='_search_is_mine')

    @api.depends('storage_kind', 'side')
    def _compute_icon(self):
        for record in self:
            record.icon = KIND_ICONS.get(record.storage_kind, '📦')
            record.side_short = ('Предлагают' if record.side == 'offer'
                                 else 'Ищут')

    @api.depends('volume', 'capacity_unit', 'date_from', 'date_to',
                 'term_ids.kind', 'term_ids.price', 'term_ids.price_unit')
    def _compute_labels(self):
        kinds = dict(TERM_KINDS)
        for record in self:
            # Паллетоместа и тонны целые, квадратные метры тоже: дробная
            # часть на плитке каталога читается как опечатка. Единица
            # склоняется по числу — иначе выходит «46 паллетоместа».
            record.volume_label = amount_with_unit(record.volume,
                                                   record.capacity_unit)
            record.period_label = record._period_text()

            named = [kinds.get(term.kind, '') for term in record.term_ids]
            record.terms_label = ', '.join(name for name in named if name)

            money = record.term_ids.filtered(
                lambda term: term.kind in MONEY_TERMS and term.price)
            if money:
                cheapest = min(money, key=lambda term: term.price)
                record.main_price = cheapest.price
                record.main_price_label = '%s ₽ %s' % (
                    int(round(cheapest.price)), cheapest.price_unit or '')
            else:
                record.main_price = 0
                record.main_price_label = 'без денег'

    def _period_text(self):
        self.ensure_one()
        if self.date_from and self.date_to:
            return '%s — %s' % (self.date_from.strftime('%d.%m.%Y'),
                                self.date_to.strftime('%d.%m.%Y'))
        if self.date_from:
            return 'с %s' % self.date_from.strftime('%d.%m.%Y')
        if self.date_to:
            return 'до %s' % self.date_to.strftime('%d.%m.%Y')
        return 'без срока'

    @api.depends('deal_ids')
    def _compute_deal_count(self):
        for record in self:
            record.deal_count = len(record.deal_ids)

    @api.depends_context('uid')
    def _compute_is_mine(self):
        mine = self.env.user._coop_partner_ids()
        for record in self:
            record.is_mine = record.owner_id.id in mine

    def _search_is_mine(self, operator, value):
        # Odoo приводит `= True` к `in {True}` и передаёт множество,
        # а не список: значение разбирается как последовательность.
        if isinstance(value, (list, tuple, set, frozenset)):
            wanted = True in value
        else:
            wanted = bool(value)
        if operator in ('!=', 'not in'):
            wanted = not wanted
        mine = list(self.env.user._coop_partner_ids())
        return [('owner_id', 'in' if wanted else 'not in', mine)]

    @api.onchange('warehouse_id')
    def _onchange_warehouse(self):
        """Город и температуру у предложения берём со склада.

        Вводить их заново — верный способ получить морозильник в одном
        городе и объявление о нём в другом.
        """
        for record in self:
            if record.warehouse_id:
                record.city = record.warehouse_id.city
                record.storage_kind = record.warehouse_id.storage_kind
                record.capacity_unit = record.warehouse_id.capacity_unit
                if not record.owner_id:
                    record.owner_id = record.warehouse_id.owner_id

    @api.constrains('side', 'warehouse_id')
    def _check_side(self):
        for record in self:
            if record.side == 'offer' and not record.warehouse_id:
                raise ValidationError(_(
                    'У предложения мощностей должен быть склад: без адреса '
                    'и температуры место никому не подойдёт.'))

    def action_publish(self):
        for record in self:
            if not record.term_ids:
                raise UserError(_(
                    'Объявление без условий опубликовать нельзя: '
                    'откликающийся не поймёт, за что берётся место.'))
            if record.warehouse_id and record.volume > record.warehouse_id.free:
                raise UserError(_(
                    'На складе свободно %(free)s, а выставляется %(vol)s. '
                    'Подрежьте объём или освободите место.',
                    free=record.warehouse_id.free, vol=record.volume))
            record.write({
                'state': 'published',
                'published_on': record.published_on or fields.Date.today(),
            })

    def action_close(self):
        self.write({'state': 'closed'})

    can_respond = fields.Boolean(
        string='Можно откликнуться', compute='_compute_can_respond',
        help='Мощности выставлены, и они не мои.')

    @api.depends_context('uid')
    @api.depends('state', 'warehouse_id.owner_id')
    def _compute_can_respond(self):
        """Тот же вопрос, что решает кнопку, и тот же, что решает отказ."""
        mine = self.env.user.coop_actor_partner_ids
        for record in self:
            record.can_respond = bool(
                record.state == 'published'
                and record.warehouse_id.owner_id not in mine)

    def action_respond(self):
        """«Отправить отклик» — как в макете (`ext-warehouse.html`).

        Заводит переговоры по сделке: место на складе передаётся в
        аренду, а аренда на платформе — это сделка со сроками, приёмкой и
        отзывами. Заводить рядом вторую сущность «отклик» незачем.
        """
        self.ensure_one()
        if not self.can_respond:
            raise UserError(_(
                'Откликнуться можно на выставленные мощности, и не на свои.'))
        me = self.env.user._coop_acting_partner()
        owner = self.warehouse_id.owner_id
        deal = self.env['coop.deal'].sudo().create({
            'name': _('Место на складе «%s»') % self.warehouse_id.name,
            'subject': 'resource',
            'way': 'rent',
            'party_a_id': owner.id,
            'party_b_id': me.id,
            'role_a': _('Передаёт'),
            'role_b': _('Принимает'),
            'author_id': self.env.user.partner_id.id,
            'city': self.warehouse_id.city or '',
            'amount': self.main_price or 0.0,
            'state': 'draft',
        })
        body = _('Отклик на свободные мощности склада «%(склад)s» от '
                 '%(кто)s. Заведены переговоры по сделке %(номер)s.',
                 warehouse=self.warehouse_id.name, who=me.display_name,
                 number=deal.number or '')
        self.env['coop.notification']._notify(
            owner, body, record=deal, kind='deal')
        deal.message_post(body=body)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Сделка %s') % (deal.number or ''),
            'res_model': 'coop.deal',
            'res_id': deal.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_matched(self):
        self.write({'state': 'matched'})

    def action_back_to_draft(self):
        self.write({'state': 'draft'})


class CoopWarehouseOfferTerm(models.Model):
    """Строка условия: на чём сходимся и почём.

    Отдельной моделью, а не набором полей у объявления: условий бывает
    четыре сразу, и у каждого своя цена и своя оговорка. Плоскими полями
    это превращается в `price_rent`, `price_custody`, `price_buyout` —
    и в пустые колонки у тех, кто сдаёт только в обмен.
    """
    _name = 'coop.warehouse.offer.term'
    _description = 'Условие объявления на бирже'
    _order = 'offer_id, sequence, id'

    offer_id = fields.Many2one(
        'coop.warehouse.offer', string='Объявление', required=True,
        ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    kind = fields.Selection(TERM_KINDS, string='Условие', required=True)
    currency_id = fields.Many2one(
        related='offer_id.currency_id', string='Валюта')
    price = fields.Monetary(
        string='Цена', currency_field='currency_id',
        help='Пусто у обмена, пая и участия в проекте: там платят не '
             'деньгами.')
    price_unit = fields.Char(
        string='За что', help='за м² в месяц, за паллетоместо в сутки.')
    note = fields.Char(string='Оговорка')

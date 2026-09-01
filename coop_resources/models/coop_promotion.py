# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Сколько мест в блоке и на сколько страниц они продаются — объявлено
# один раз, в наборе мест. Два объявления этих чисел разошлись бы при
# первой же правке, и места перестали бы соответствовать выдаче.
from ..data.coop_promotion_slots import PROMOTED_PAGES, SLOTS_PER_PAGE  # noqa: F401


class CoopPromotionSlot(models.Model):
    """Место в выдаче каталога — страница и строка в платном блоке.

    Продвижение покупается местом, а не абстрактной ставкой (решение
    владельца от 2026-09-01, по образцу контекстной выдачи). Первая строка
    первой страницы и третья строка пятой — это разный охват и разная
    цена, и участник выбирает, что ему нужно, а не торгуется вслепую.

    Мест конечное число, и в этом весь смысл: одно место занято одним
    объявлением на срок. Сколько объявлений продвигает один владелец —
    не ограничено, он просто выкупает несколько мест.
    """
    _name = 'coop.promotion.slot'
    _description = 'Место в выдаче'
    _order = 'page, position'

    name = fields.Char(string='Место', compute='_compute_name', store=True)
    page = fields.Integer(string='Страница', required=True, index=True)
    position = fields.Integer(string='Строка в блоке', required=True)

    price_per_day = fields.Integer(
        string='Цена, токенов в сутки', required=True,
        help='Зависит от охвата: чем ближе к началу выдачи, тем дороже.')
    reach_share = fields.Float(
        string='Доля просмотров, %', digits=(5, 1),
        help='Оценка того, какая часть смотрящих каталог доходит до этого '
             'места. Считается от затухания внимания по строкам и '
             'страницам, а не измеряется — измерять пока нечего.')

    is_taken = fields.Boolean(
        string='Занято', compute='_compute_is_taken',
        search='_search_is_taken')
    occupied_until = fields.Datetime(
        string='Занято до', compute='_compute_is_taken')
    resource_id = fields.Many2one(
        'coop.resource', string='Сейчас показывается', compute='_compute_is_taken')

    _sql_constraints = [
        ('place_uniq', 'unique(page, position)', 'Такое место уже заведено.'),
    ]

    def _search_is_taken(self, operator, value):
        """Поиск по занятости.

        Признак считается на лету — по нему нельзя отобрать записи без
        этого метода, а отбирать надо: окно продвижения показывает только
        свободные места.
        """
        if operator not in ('=', '!='):
            raise UserError(_('По занятости можно искать только равенством.'))
        now = fields.Datetime.now()
        busy = self.env['coop.promotion'].sudo().search([
            ('date_to', '>', now)]).mapped('slot_id').ids
        looking_for_taken = (operator == '=') == bool(value)
        return [('id', 'in' if looking_for_taken else 'not in', busy)]

    @api.depends('page', 'position')
    def _compute_name(self):
        for record in self:
            record.name = 'Страница %s, строка %s' % (record.page, record.position)

    def _compute_is_taken(self):
        now = fields.Datetime.now()
        active = self.env['coop.promotion'].sudo().search([
            ('slot_id', 'in', self.ids), ('date_to', '>', now),
        ], order='date_to desc')
        by_slot = {}
        for promotion in active:
            by_slot.setdefault(promotion.slot_id.id, promotion)
        for record in self:
            promotion = by_slot.get(record.id)
            record.is_taken = bool(promotion)
            record.occupied_until = promotion.date_to if promotion else False
            record.resource_id = promotion.resource_id if promotion else False


class CoopPromotion(models.Model):
    """Оплаченный показ объявления на конкретном месте.

    Списание — вперёд и целиком за весь срок. Посуточное списание
    потребовало бы задания, которое ходит по всем объявлениям и снимает
    токены, — а значит, и разбирательств, что делать, когда баланс
    кончился в середине срока. Оплата вперёд этот класс вопросов снимает.
    """
    _name = 'coop.promotion'
    _description = 'Продвижение объявления'
    _order = 'date_to desc, id desc'

    resource_id = fields.Many2one(
        'coop.resource', string='Объявление', required=True,
        ondelete='cascade', index=True)
    slot_id = fields.Many2one(
        'coop.promotion.slot', string='Место', required=True,
        ondelete='restrict', index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Плательщик', required=True, index=True)
    days = fields.Integer(string='Дней', required=True, default=7)
    price_per_day = fields.Integer(string='Цена суток, токенов', required=True)
    total_tokens = fields.Integer(
        string='Списано токенов', compute='_compute_total', store=True)
    date_from = fields.Datetime(string='С', required=True)
    date_to = fields.Datetime(string='По', required=True, index=True)
    transaction_id = fields.Many2one(
        'coop.token.transaction', string='Движение токенов', readonly=True)

    _sql_constraints = [
        ('days_positive', 'check(days > 0)', 'Срок должен быть больше нуля.'),
    ]

    @api.depends('price_per_day', 'days')
    def _compute_total(self):
        for record in self:
            record.total_tokens = record.price_per_day * record.days

    @api.model
    def promote(self, resource, slot, days):
        """Занять место под объявление и списать токены.

        Место занимается целиком на срок: два объявления на одной строке
        одной страницы одновременно показать нельзя, и очередь тут
        честнее аукциона — кто первый занял, тот и стоит, пока не выйдет
        срок.
        """
        resource.ensure_one()
        slot.ensure_one()
        days = int(days)
        if days <= 0:
            raise UserError(_('Срок должен быть больше нуля.'))

        # Продвигать можно только своё объявление. Проверка здесь, а не
        # только в интерфейсе: списываются токены владельца объявления, и
        # без неё любой участник мог потратить чужой баланс.
        user = self.env.user
        if (resource.owner_id != user.partner_id
                and not user.has_group('base.group_system')):
            raise UserError(_(
                'Продвинуть можно только своё объявление. «%(name)s» '
                'принадлежит другому участнику.', name=resource.name))

        now = fields.Datetime.now()
        busy = self.search([
            ('slot_id', '=', slot.id), ('date_to', '>', now),
            ('resource_id', '!=', resource.id),
        ], limit=1)
        if busy:
            raise UserError(_(
                'Место «%(slot)s» занято до %(until)s. Выберите другое — '
                'свободные показаны в списке с ценой и охватом.',
                slot=slot.name, until=fields.Datetime.to_string(busy.date_to)))

        payer = resource.owner_id
        total = slot.price_per_day * days
        transaction = payer.coop_token_spend(
            total, 'promotion',
            _('Продвижение «%(name)s» на месте «%(slot)s», %(days)s дн.',
              name=resource.name, slot=slot.name, days=days),
            record=resource)

        # Продление считается от конца текущего показа, а не от «сейчас»:
        # иначе продливший заранее терял бы оплаченные сутки.
        current = self.search([
            ('slot_id', '=', slot.id), ('resource_id', '=', resource.id),
            ('date_to', '>', now),
        ], order='date_to desc', limit=1)
        start = current.date_to if current else now
        end = start + timedelta(days=days)

        promotion = self.create({
            'resource_id': resource.id,
            'slot_id': slot.id,
            'partner_id': payer.id,
            'days': days,
            'price_per_day': slot.price_per_day,
            'date_from': start,
            'date_to': end,
            'transaction_id': transaction.id,
        })
        resource.write({'promoted_until': end, 'promotion_slot_id': slot.id})
        resource.message_post(body=_(
            'Объявление занимает место «%(slot)s» до %(until)s. '
            'Списано %(total)s токенов.',
            slot=slot.name, until=fields.Datetime.to_string(end), total=total))
        self.env['coop.resource']._recompute_catalog_rank()
        return promotion


class CoopResourcePromote(models.TransientModel):
    """Окно «Продвинуть объявление»: выбор места и срока."""
    _name = 'coop.resource.promote'
    _description = 'Продвижение объявления'

    resource_id = fields.Many2one('coop.resource', string='Объявление', required=True)
    slot_id = fields.Many2one(
        'coop.promotion.slot', string='Место', required=True,
        domain="[('is_taken', '=', False)]")
    days = fields.Integer(string='Срок, дней', default=7, required=True)

    price_per_day = fields.Integer(
        string='Цена суток, токенов', related='slot_id.price_per_day')
    reach_share = fields.Float(
        string='Доля просмотров, %', related='slot_id.reach_share')
    total_tokens = fields.Integer(string='Итого токенов', compute='_compute_total')
    balance = fields.Integer(string='На балансе', compute='_compute_total')
    free_slots = fields.Integer(
        string='Свободных мест', compute='_compute_total')

    @api.depends('slot_id', 'days', 'resource_id')
    def _compute_total(self):
        Slot = self.env['coop.promotion.slot']
        for record in self:
            record.total_tokens = (record.slot_id.price_per_day or 0) * max(0, record.days)
            record.balance = record.resource_id.owner_id.coop_token_balance
            record.free_slots = len(Slot.search([]).filtered(lambda s: not s.is_taken))

    def action_promote(self):
        self.ensure_one()
        self.env['coop.promotion'].promote(self.resource_id, self.slot_id, self.days)
        return {'type': 'ir.actions.act_window_close'}

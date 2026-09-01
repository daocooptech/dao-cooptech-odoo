# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoopPromotion(models.Model):
    """Продвижение объявления за токены платформы.

    Устроено ставкой, а не фиксированной ценой (решение владельца от
    2026-09-01, по образцу контекстной рекламы). Владелец объявления
    назначает, сколько токенов в сутки готов платить; среди продвигаемых
    объявления показываются по убыванию ставки.

    Почему ставка, а не прайс-лист. При фиксированной цене продвижение
    либо дёшево — и тогда в «топе» оказываются все, то есть никто, — либо
    дорого, и тогда им не пользуется никто. Ставка решает это сама:
    место в выдаче стоит ровно столько, во сколько его оценивают
    участники, и цену никто не назначает сверху.

    Списание — вперёд и целиком за весь срок. Посуточное списание
    потребовало бы регламентного задания, которое ходит по всем
    объявлениям и снимает токены, — а значит, и разбирательств, что
    делать, когда баланс кончился в середине срока. Оплата вперёд этот
    класс вопросов снимает.
    """
    _name = 'coop.promotion'
    _description = 'Продвижение объявления'
    _order = 'create_date desc'

    resource_id = fields.Many2one(
        'coop.resource', string='Объявление', required=True,
        ondelete='cascade', index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Плательщик', required=True, index=True)
    bid = fields.Integer(
        string='Ставка, токенов в сутки', required=True,
        help='Чем выше ставка, тем выше объявление среди продвигаемых.')
    days = fields.Integer(string='Дней', required=True, default=7)
    total_tokens = fields.Integer(
        string='Списано токенов', compute='_compute_total', store=True)
    date_from = fields.Datetime(string='С', required=True)
    date_to = fields.Datetime(string='По', required=True)
    transaction_id = fields.Many2one(
        'coop.token.transaction', string='Движение токенов', readonly=True)

    _sql_constraints = [
        ('bid_positive', 'check(bid > 0)', 'Ставка должна быть больше нуля.'),
        ('days_positive', 'check(days > 0)', 'Срок должен быть больше нуля.'),
    ]

    @api.depends('bid', 'days')
    def _compute_total(self):
        for record in self:
            record.total_tokens = record.bid * record.days

    @api.model
    def promote(self, resource, bid, days):
        """Продвинуть объявление: списать токены и назначить срок.

        Продление считается от текущего конца показа, а не от «сейчас»:
        иначе продливший заранее терял бы оплаченные сутки.
        """
        resource.ensure_one()
        bid, days = int(bid), int(days)
        if bid <= 0 or days <= 0:
            raise UserError(_('Ставка и срок должны быть больше нуля.'))

        payer = resource.owner_id
        total = bid * days
        transaction = payer.coop_token_spend(
            total, 'promotion',
            _('Продвижение «%(name)s»: %(bid)s токенов в сутки на %(days)s дн.',
              name=resource.name, bid=bid, days=days),
            record=resource)

        now = fields.Datetime.now()
        start = resource.promoted_until if (
            resource.promoted_until and resource.promoted_until > now) else now
        end = start + timedelta(days=days)

        promotion = self.create({
            'resource_id': resource.id,
            'partner_id': payer.id,
            'bid': bid,
            'days': days,
            'date_from': start,
            'date_to': end,
            'transaction_id': transaction.id,
        })
        # Ставка на объявлении — наибольшая из действующих: участник мог
        # поднять её, не дожидаясь конца прошлого периода.
        resource.write({
            'promoted_until': end,
            'promotion_bid': max(bid, resource.promotion_bid or 0),
        })
        resource.message_post(body=_(
            'Объявление продвигается до %(until)s, ставка %(bid)s токенов в сутки.',
            until=fields.Datetime.to_string(end), bid=bid))
        return promotion


class CoopResourcePromote(models.TransientModel):
    """Окно «Продвинуть объявление»."""
    _name = 'coop.resource.promote'
    _description = 'Продвижение объявления'

    resource_id = fields.Many2one('coop.resource', string='Объявление', required=True)
    bid = fields.Integer(string='Ставка, токенов в сутки', default=5, required=True)
    days = fields.Integer(string='Срок, дней', default=7, required=True)
    total_tokens = fields.Integer(string='Итого токенов', compute='_compute_total')
    balance = fields.Integer(string='На балансе', compute='_compute_total')
    competing_bid = fields.Integer(
        string='Наибольшая ставка сейчас', compute='_compute_total',
        help='Максимальная ставка среди объявлений, продвигаемых прямо '
             'сейчас. Ставка выше этой поднимет объявление на первое место.')

    @api.depends('bid', 'days', 'resource_id')
    def _compute_total(self):
        for record in self:
            record.total_tokens = max(0, record.bid) * max(0, record.days)
            record.balance = record.resource_id.owner_id.coop_token_balance
            promoted = self.env['coop.resource'].search(
                [('is_promoted', '=', True)], order='promotion_bid desc', limit=1)
            record.competing_bid = promoted.promotion_bid if promoted else 0

    def action_promote(self):
        self.ensure_one()
        self.env['coop.promotion'].promote(self.resource_id, self.bid, self.days)
        return {'type': 'ir.actions.act_window_close'}

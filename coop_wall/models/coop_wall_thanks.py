# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .coop_wall_comment import WALL_MODELS

# Пороги — предложение экономиста (Матчасть, 24 сентября 2026). Цифры
# утверждает сообщество правилом с датой вступления в силу; до тех пор —
# эти. Слов об оплате и расчётах в сообщениях нет: владелец 24 сентября
# 2026 — «ни за что мы не рассчитываемся, это же подарок».
RUB_MIN, RUB_MAX, RUB_MONTH = 10, 5000, 15000
TON_MAX = 1000

STATES = [
    ('declared', 'Заявлена'),
    ('confirmed', 'Подтверждена автором'),
    ('unconfirmed', 'Не подтверждена'),
    ('returned', 'Возвращена'),
    ('disputed', 'Спорная'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_thanks_on = fields.Boolean(
        string='Принимаю подарки за записи',
        help='Под вашими записями на стене появится «Поблагодарить»: '
             'подарок рублями по СБП или в TON. Он приходит вам напрямую, '
             'платформа его не получает.')
    coop_thanks_sbp = fields.Char(
        string='Телефон или ссылка СБП',
        help='Видно только тому, кто решил вас поблагодарить, и только '
             'пока приём подарков включён.')


class CoopWallThanks(models.Model):
    """Благодарность автору записи на стене.

    Владелец 24 сентября 2026 (решение 406): рубли — по ссылке СБП автора,
    TON — подарком, кнопка «Поблагодарить» со значком подарка.

    Платформа денег не касается. Рубли даритель переводит в своём банке
    по СБП автора, TON — из своего кошелька на адрес автора; здесь только
    запись о том, что благодарность заявлена, и отметка автора, пришли ли
    деньги. Иначе, по заключению юриста, это был бы перевод денежных
    средств без лицензии (161-ФЗ).

    Что видно: автору — кто и сколько; всем остальным — только число
    поблагодаривших, без сумм (экономист: иначе стена становится денежным
    рейтингом).
    """
    _name = 'coop.wall.thanks'
    _description = 'Благодарность автору записи'
    _order = 'date desc, id desc'

    post_id = fields.Many2one(
        'mail.message', string='Запись', required=True, index=True,
        ondelete='cascade')
    sender_id = fields.Many2one(
        'res.partner', string='Кто благодарит', required=True, index=True,
        ondelete='cascade')
    recipient_id = fields.Many2one(
        'res.partner', string='Автор', required=True, index=True,
        ondelete='cascade')
    channel = fields.Selection(
        [('sbp', 'Рубли по СБП'), ('ton', 'TON')],
        string='Чем', required=True)
    amount = fields.Float(string='Сколько', required=True)
    currency = fields.Char(
        string='Валюта', compute='_compute_currency', store=True)
    state = fields.Selection(
        STATES, string='Состояние', required=True, default='declared',
        index=True)
    date = fields.Datetime(
        string='Когда', required=True, default=fields.Datetime.now)

    _positive = models.Constraint('CHECK (amount > 0)', 'Сумма должна быть больше нуля.')
    _not_self = models.Constraint(
        'CHECK (sender_id != recipient_id)', 'Себя поблагодарить нельзя.')

    @api.depends('channel')
    def _compute_currency(self):
        for record in self:
            record.currency = 'TON' if record.channel == 'ton' else '₽'

    # ── Вспомогательное ─────────────────────────────────────────────

    def _coop_post(self, post_id):
        post = self.env['mail.message'].browse(post_id).exists()
        if not post or post.model not in WALL_MODELS or post.message_type != 'comment':
            raise UserError(_("Запись не найдена."))
        post.check_access('read')
        return post

    @api.model
    def _coop_ton_address(self, partner):
        if 'coop.wallet.address' not in self.env:
            return False
        address = self.env['coop.wallet.address'].sudo().search([
            ('wallet_id.partner_id', '=', partner.id),
            ('network_id.code', '=', 'ton'),
        ], limit=1)
        return address.address or False

    def _coop_to_dict(self):
        return [{
            'id': t.id,
            'sender_id': t.sender_id.id,
            'sender_name': t.sender_id.name,
            'channel': t.channel,
            'amount': t.amount,
            'currency': t.currency,
            'state': t.state,
            'state_label': dict(STATES)[t.state],
            'date': fields.Datetime.to_string(t.date),
        } for t in self]

    # ── Для браузера ─────────────────────────────────────────────────

    @api.model
    def coop_info(self, post_id):
        """Что показать в окне «Поблагодарить» для этой записи."""
        post = self._coop_post(post_id)
        me = self.env.user.partner_id
        author = post.sudo().author_id
        own = author == me
        result = {
            'own': own,
            'author_name': author.name or '',
            'can_thank': False,
            'reason': '',
            'sbp': False,
            'ton_address': False,
            'received': [],
            'limits': {'rub_min': RUB_MIN, 'rub_max': RUB_MAX, 'ton_max': TON_MAX},
        }
        if own:
            result['received'] = self.sudo().search(
                [('post_id', '=', post.id)])._coop_to_dict()
            return result
        if not author or not author.sudo().coop_thanks_on:
            result['reason'] = _("Автор не принимает благодарности.")
            return result
        result['can_thank'] = True
        result['sbp'] = author.sudo().coop_thanks_sbp or False
        result['ton_address'] = self._coop_ton_address(author)
        if not result['sbp'] and not result['ton_address']:
            result['can_thank'] = False
            result['reason'] = _("Автор не указал, куда принимать благодарности.")
        return result

    @api.model
    def coop_declare(self, post_id, channel, amount, understood):
        """Даритель отмечает, что подарок отправлен."""
        if not understood:
            raise UserError(_("Отметьте, что понимаете: это подарок."))
        post = self._coop_post(post_id)
        me = self.env.user.partner_id
        author = post.sudo().author_id
        if author == me:
            raise UserError(_("Себя поблагодарить нельзя."))
        if not author.sudo().coop_thanks_on:
            raise UserError(_("Автор не принимает благодарности."))
        if hasattr(me, 'coop_require_level'):
            me.coop_require_level('identity', _("поблагодарить автора"))
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise UserError(_("Укажите сумму подарка числом."))
        if channel == 'sbp':
            if not author.sudo().coop_thanks_sbp:
                raise UserError(_("Автор не указал СБП."))
            if not RUB_MIN <= amount <= RUB_MAX:
                raise UserError(_("Подарок рублями — от %(lo)s до %(hi)s ₽.",
                                  lo=RUB_MIN, hi=RUB_MAX))
            month = self.sudo().search([
                ('sender_id', '=', me.id), ('recipient_id', '=', author.id),
                ('channel', '=', 'sbp'),
                ('state', 'in', ('declared', 'confirmed')),
                ('date', '>=', fields.Datetime.now() - timedelta(days=30)),
            ])
            if sum(month.mapped('amount')) + amount > RUB_MONTH:
                raise UserError(_(
                    "Одному автору — не больше %(hi)s ₽ подарков за месяц.",
                    hi=RUB_MONTH))
        elif channel == 'ton':
            if not self._coop_ton_address(author):
                raise UserError(_("Автор не указал адрес TON."))
            if not 0 < amount <= TON_MAX:
                raise UserError(_("Подарок в TON — не больше %(hi)s.", hi=TON_MAX))
        else:
            raise UserError(_("Неизвестный способ."))
        thanks = self.sudo().create({
            'post_id': post.id,
            'sender_id': me.id,
            'recipient_id': author.id,
            'channel': channel,
            'amount': amount,
        })
        return thanks._coop_to_dict()[0]

    @api.model
    def coop_set_state(self, thanks_id, state):
        """Автор отмечает: пришло, не пришло, вернул."""
        thanks = self.sudo().browse(thanks_id).exists()
        if not thanks:
            raise UserError(_("Благодарность не найдена."))
        if thanks.recipient_id != self.env.user.partner_id:
            raise AccessError(_("Отмечать может только автор записи."))
        if state not in ('confirmed', 'unconfirmed', 'returned'):
            raise UserError(_("Такого состояния автор не ставит."))
        thanks.state = state
        return thanks._coop_to_dict()[0]

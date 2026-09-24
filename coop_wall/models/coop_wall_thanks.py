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

# Токены по сетям. Владелец 24 сентября 2026: «сделай вместо TON вкладку
# „Токенами“ и там уже выбор блокчейна, сети, комиссии и т. д.». Сеть —
# из справочника кошелька (`coop.wallet.network`), и только та, где у
# автора есть адрес. Своя сеть кооператива (`koop`, COOP) в подарки не
# идёт: COOP между участниками не передаётся (решения 243а, 406).
#
# Комиссия — ориентир на осень 2026 года, не котировка: её платит
# даритель, а точную сумму показывает его кошелёк перед подписью.
TOKENS = {
    'btc': [('BTC', 'BTC')],
    'eth': [('ETH', 'ETH'), ('USDT', 'USDT · ERC-20'), ('USDC', 'USDC · ERC-20')],
    'bnb': [('BNB', 'BNB'), ('USDT', 'USDT · BEP-20')],
    'ton': [('TON', 'TON'), ('USDT', 'USDT · TON')],
    'sol': [('SOL', 'SOL'), ('USDC', 'USDC · SPL')],
}
FEE_HINTS = {
    'btc': 'обычно от 0,5 до 3 $, зависит от загрузки сети',
    'eth': 'обычно от 0,3 до 3 $; за USDT и USDC — дороже, чем за ETH',
    'bnb': 'около 0,05 $',
    'ton': 'около 0,01–0,05 TON',
    'sol': 'меньше 0,01 $',
}
NO_GIFT_NETWORKS = ('koop',)

# Налоги в окне подарка. Владелец 24 сентября 2026: «и налоги, если
# возникают». Строки — от бухгалтера (Матчасть, «Налоги с подарков за
# записи», 24.09.2026); платформа налоговым агентом не становится: денег
# и токенов она не передаёт, только показывает, что кому придётся
# сделать. Главное: токены в подарок от человека, который не
# родственник, с 01.01.2025 облагаются НДФЛ 13% (п. 18.1 ст. 217 НК в
# ред. 418-ФЗ), рубли — нет.
TAX_NOTES = {
    ('person', 'person', 'sbp'): [
        "Налога нет: денежный подарок от человека не облагается "
        "(п. 18.1 ст. 217 НК).",
    ],
    ('person', 'person', 'token'): [
        "С вас налога нет.",
        "Получатель, если вы не родственники, заплатит 13% НДФЛ со стоимости "
        "токенов в рублях на день зачисления: подаст 3-НДФЛ до 30 апреля "
        "следующего года и заплатит до 15 июля (п. 18.1 ст. 217, ст. 228 НК).",
    ],
    ('org', 'person', 'sbp'): [
        "Подарки одному человеку сверх 4 000 ₽ за год облагаются: удержите "
        "13% НДФЛ и покажите в 6-НДФЛ (п. 28 ст. 217, ст. 226 НК).",
        "Получателю ничего подавать не нужно.",
    ],
    ('org', 'person', 'token'): [
        "Сверх 4 000 ₽ за год на человека — 13% НДФЛ. Удержать его не из "
        "чего: до 25 февраля сообщите налоговой и получателю "
        "(п. 5 ст. 226 НК).",
        "Получатель оплатит по уведомлению налоговой до 1 декабря, "
        "декларация не нужна (п. 6 ст. 228 НК).",
    ],
    ('any', 'org', 'any'): [
        "Для организации подарок — доход: 6% на УСН «доходы» или 25% на "
        "общем режиме, в день поступления (п. 8 ст. 250 НК). Некоммерческой "
        "организации — не облагается, если принят как пожертвование на "
        "уставные цели и учтён отдельно (пп. 1 п. 2 ст. 251 НК).",
    ],
}
RECEIVED_NOTES = {
    'sbp': "Денежные подарки от людей налогом не облагаются; от организаций "
           "до 4 000 ₽ за год — тоже, сверх — налог удерживает даритель.",
    'token': "Подарки токенами от людей, которые вам не родственники, "
             "облагаются НДФЛ 13% со стоимости на день зачисления: подайте "
             "3-НДФЛ до 30 апреля следующего года (п. 18.1 ст. 217, ст. 228 "
             "НК). За неподанную декларацию штраф — от 1 000 ₽.",
}


def _kind(partner):
    return 'org' if partner.is_company else 'person'


def tax_notes(sender, recipient, channel):
    if _kind(recipient) == 'org':
        return TAX_NOTES[('any', 'org', 'any')]
    return TAX_NOTES.get((_kind(sender), 'person', channel), [])

# Названия — про подарок, а не про благодарность: окно называется
# «Подарки за запись», и «Заявлена» рядом с ним читалось вразнобой.
STATES = [
    ('declared', 'Отправлен'),
    ('confirmed', 'Пришёл'),
    ('unconfirmed', 'Не пришёл'),
    ('returned', 'Возвращён'),
    ('disputed', 'Спорный'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_thanks_on = fields.Boolean(
        string='Принимаю подарки за записи',
        help='Под вашими записями на стене появится «Поблагодарить»: '
             'подарок рублями по СБП или токенами. Он приходит вам напрямую, '
             'платформа его не получает.')
    coop_thanks_sbp = fields.Char(
        string='Телефон или ссылка СБП',
        help='Видно только тому, кто решил вас поблагодарить, и только '
             'пока приём подарков включён.')


class CoopWallThanks(models.Model):
    """Благодарность автору записи на стене.

    Владелец 24 сентября 2026 (решение 406): рубли — по ссылке СБП автора,
    токены — подарком в выбранной сети, кнопка «Поблагодарить» со значком
    подарка.

    Платформа денег не касается. Рубли даритель переводит в своём банке
    по СБП автора, токены — из своего кошелька на адрес автора в сети;
    здесь только
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
        [('sbp', 'Рублями по СБП'), ('token', 'Токенами')],
        string='Чем', required=True)
    network_id = fields.Many2one(
        'coop.wallet.network', string='Сеть', ondelete='restrict')
    token = fields.Char(string='Токен')
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

    @api.depends('channel', 'token')
    def _compute_currency(self):
        for record in self:
            record.currency = record.token if record.channel == 'token' else '₽'

    # ── Вспомогательное ─────────────────────────────────────────────

    def _coop_post(self, post_id):
        post = self.env['mail.message'].browse(post_id).exists()
        if not post or post.model not in WALL_MODELS or post.message_type != 'comment':
            raise UserError(_("Запись не найдена."))
        post.check_access('read')
        return post

    @api.model
    def _coop_networks(self, partner):
        """Сети, где у автора есть адрес, — с токенами и комиссией."""
        if 'coop.wallet.address' not in self.env:
            return []
        addresses = self.env['coop.wallet.address'].sudo().search([
            ('wallet_id.partner_id', '=', partner.id),
            ('network_id.code', 'not in', NO_GIFT_NETWORKS),
            ('network_id.active', '=', True),
        ])
        result, seen = [], set()
        for address in addresses.sorted(lambda a: (a.network_id.sequence, a.id)):
            network = address.network_id
            if network.id in seen:
                continue
            seen.add(network.id)
            tokens = TOKENS.get(network.code) or [(network.symbol, network.symbol)]
            result.append({
                'id': network.id,
                'code': network.code,
                'name': network.name,
                'address': address.address,
                'tokens': [{'symbol': s, 'label': l} for s, l in tokens],
                'fee_hint': FEE_HINTS.get(network.code, ''),
            })
        return result

    def _coop_to_dict(self):
        return [{
            'id': t.id,
            'sender_id': t.sender_id.id,
            'sender_name': t.sender_id.name,
            'channel': t.channel,
            'network': t.network_id.name or '',
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
            'networks': [],
            'received': [],
            'limits': {'rub_min': RUB_MIN, 'rub_max': RUB_MAX},
            'taxes': {},
            'received_notes': [],
        }
        if own:
            received = self.sudo().search([('post_id', '=', post.id)])
            result['received'] = received._coop_to_dict()
            result['received_notes'] = [
                RECEIVED_NOTES[c] for c in ('sbp', 'token')
                if c in received.mapped('channel')]
            # Автор видит и то, как его благодарят другие: владелец
            # 24 сентября 2026 открыл «Поблагодарить» на своей записи и
            # «вилки, как я могу отблагодарить», не увидел.
            me_su = me.sudo()
            result['own_thanks_on'] = bool(me_su.coop_thanks_on)
            result['sbp'] = me_su.coop_thanks_sbp or False
            result['networks'] = self._coop_networks(me)
            return result
        if not author or not author.sudo().coop_thanks_on:
            result['reason'] = _("Автор не принимает благодарности.")
            return result
        result['can_thank'] = True
        result['sbp'] = author.sudo().coop_thanks_sbp or False
        result['networks'] = self._coop_networks(author)
        result['taxes'] = {c: tax_notes(me, author.sudo(), c) for c in ('sbp', 'token')}
        if not result['sbp'] and not result['networks']:
            result['can_thank'] = False
            result['reason'] = _("Автор не указал, куда принимать благодарности.")
        return result

    @api.model
    def coop_declare(self, post_id, channel, amount, understood,
                     network_id=False, token=False):
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
        elif channel == 'token':
            network = next((n for n in self._coop_networks(author)
                            if n['id'] == network_id), None)
            if not network:
                raise UserError(_("У автора нет адреса в этой сети."))
            if token not in [t['symbol'] for t in network['tokens']]:
                raise UserError(_("Этот токен в выбранной сети не принимается."))
            if amount <= 0:
                raise UserError(_("Сумма подарка должна быть больше нуля."))
        else:
            raise UserError(_("Неизвестный способ."))
        thanks = self.sudo().create({
            'post_id': post.id,
            'sender_id': me.id,
            'recipient_id': author.id,
            'channel': channel,
            'network_id': network_id if channel == 'token' else False,
            'token': token if channel == 'token' else False,
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

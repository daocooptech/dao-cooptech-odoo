# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Цифровая валюта как предмет обмена. Токен платформы (КООП) сюда не
# входит: он не цифровая валюта, а внутренняя единица (решения 117, 243).
ASSETS = [
    ('BTC', 'Bitcoin (BTC)'),
    ('ETH', 'Ether (ETH)'),
    ('USDT', 'Tether (USDT)'),
    ('TON', 'Toncoin (TON)'),
    ('SOL', 'Solana (SOL)'),
    ('BNB', 'BNB'),
]

# Сеть, в которой ходит монета. USDT бывает в нескольких — и перевод в
# чужую сеть означает потерю средств, поэтому сеть — отдельное поле.
ASSET_NETWORKS = {
    'BTC': ('btc',),
    'ETH': ('eth',),
    'USDT': ('eth', 'ton', 'bnb', 'sol'),
    'TON': ('ton',),
    'SOL': ('sol',),
    'BNB': ('bnb',),
}

# Порог, после которого сторонам предлагается подтвердить личность друг
# другу. Обменник не субъект ст. 5 ФЗ-115, но банк стороны спросит, а без
# этого — ст. 174, 174.1 УК у участников (разбор юриста, 2.3, WARN).
IDENTIFY_FROM = 600_000

NOTICE = ('Здесь покупают и продают цифровую валюту как имущество. '
          'Расплачиваться цифровой валютой за товары и услуги в России '
          'нельзя — ни здесь, ни где-либо ещё.')


class CoopCryptoOffer(models.Model):
    """Объявление о покупке или продаже цифровой валюты.

    Решение 392: «мы делаем функционал биржи». Разбор юриста (2.6):
    единственная конструкция, работающая без статусов, — доска
    объявлений. Платформа сводит людей, показывает доверие и историю и
    фиксирует состоявшийся обмен после него; ни рублёвый, ни криптовый
    поток через неё не идут, ключей она не держит.

    Правила интерфейса из разбора (2.3), зашитые здесь, а не в
    инструкцию модератору:

    - обмен не связан со сделкой или ресурсом платформы — таких полей нет
      вовсе: связка обмена с покупкой — это притворная оплата (п. 2 ст. 170
      ГК);
    - раздел только для вошедших участников: ни публичной страницы, ни
      рассылки — запрет предложения цифровой валюты неопределённому кругу;
    - ключей и средств платформа не держит: в объявлении — только
      публичный адрес, если его захотят показать;
    - крупная сумма — предупреждение о подтверждении личности.
    """
    _name = 'coop.crypto.offer'
    _description = 'Объявление об обмене цифровой валюты'
    _inherit = ['mail.thread']
    _order = 'published_on desc, id desc'

    name = fields.Char(string='Заголовок', compute='_compute_name', store=True)
    side = fields.Selection([
        ('sell', 'Продаю'),
        ('buy', 'Покупаю'),
    ], string='Сторона', required=True, default='sell', index=True, tracking=True)
    asset = fields.Selection(ASSETS, string='Цифровая валюта', required=True,
                             default='USDT', index=True, tracking=True)
    network_id = fields.Many2one(
        'coop.wallet.network', string='Сеть', required=True, index=True,
        domain="[('code', '!=', 'koop')]")
    author_id = fields.Many2one(
        'res.partner', string='Кто', required=True, index=True,
        default=lambda self: self.env.user.partner_id, tracking=True)
    trust = fields.Integer(related='author_id.coop_trust', string='Доверие, %')
    city = fields.Char(string='Город', index=True)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.ref('base.RUB', raise_if_not_found=False))
    price = fields.Monetary(string='Цена за единицу, ₽', required=True, tracking=True)
    amount_min = fields.Float(string='От, единиц', digits=(16, 8))
    amount_max = fields.Float(string='До, единиц', digits=(16, 8), required=True)
    rub_max = fields.Monetary(string='Объём до, ₽', compute='_compute_rub', store=True)
    rub_bank = fields.Boolean(string='Перевод на счёт')
    rub_sbp = fields.Boolean(string='СБП')
    rub_cash = fields.Boolean(string='Наличные при встрече')
    terms = fields.Text(string='Условия',
                        help='Как проходит обмен: кто первым переводит, сколько '
                             'ждать подтверждений в сети.')
    state = fields.Selection([
        ('active', 'Активно'),
        ('paused', 'На паузе'),
        ('closed', 'Снято'),
    ], string='Состояние', default='active', required=True, index=True, tracking=True)
    published_on = fields.Datetime(string='Опубликовано', default=fields.Datetime.now,
                                   index=True)
    trade_ids = fields.One2many('coop.crypto.trade', 'offer_id', string='Обмены')
    trade_count = fields.Integer(compute='_compute_trade_count')
    done_count = fields.Integer(string='Обменов состоялось', compute='_compute_trade_count')
    is_mine = fields.Boolean(compute='_compute_is_mine', search='_search_is_mine')
    methods_label = fields.Char(compute='_compute_labels')
    limits_label = fields.Char(compute='_compute_labels')
    price_label = fields.Char(compute='_compute_labels')
    needs_identify = fields.Boolean(compute='_compute_rub', store=True)
    notice = fields.Html(compute='_compute_notice', sanitize=False)

    @api.depends('side', 'asset', 'network_id')
    def _compute_name(self):
        sides = dict(self._fields['side'].selection)
        for offer in self:
            network = offer.network_id.name or ''
            offer.name = '%s %s%s' % (sides.get(offer.side, ''), offer.asset or '',
                                      (' · %s' % network) if offer.asset == 'USDT' and network else '')

    @api.depends('price', 'amount_max')
    def _compute_rub(self):
        for offer in self:
            offer.rub_max = (offer.price or 0) * (offer.amount_max or 0)
            offer.needs_identify = offer.rub_max >= IDENTIFY_FROM

    def _compute_trade_count(self):
        groups = dict(((offer.id, state), count) for offer, state, count in
                      self.env['coop.crypto.trade'].sudo()._read_group(
                          [('offer_id', 'in', self.ids)], ['offer_id', 'state'], ['__count']))
        for offer in self:
            offer.trade_count = sum(v for (oid, _s), v in groups.items() if oid == offer.id)
            offer.done_count = groups.get((offer.id, 'done'), 0)

    def _compute_is_mine(self):
        mine = self.env.user.partner_id
        for offer in self:
            offer.is_mine = offer.author_id == mine

    def _search_is_mine(self, operator, value):
        if operator != 'in':  # Odoo 19: признак — оператором in
            return NotImplemented
        return [('author_id', '=', self.env.user.partner_id.id)]

    def _compute_labels(self):
        for offer in self:
            methods = [label for flag, label in (
                (offer.rub_sbp, 'СБП'), (offer.rub_bank, 'Перевод'), (offer.rub_cash, 'Наличные'))
                if flag]
            offer.methods_label = ' · '.join(methods)
            offer.limits_label = '%s – %s %s' % (_fmt(offer.amount_min), _fmt(offer.amount_max),
                                                 offer.asset or '')
            offer.price_label = '{:,.2f} ₽'.format(offer.price or 0).replace(',', ' ').replace('.', ',')

    def _compute_notice(self):
        for offer in self:
            parts = [Markup('<div class="alert alert-info mb-2">%s</div>') % NOTICE]
            if offer.needs_identify:
                parts.append(Markup('<div class="alert alert-warning mb-2">%s</div>') % _(
                    'Объём от 600 000 ₽: стороны подтверждают личность друг другу до '
                    'обмена. Банк стороны всё равно спросит, откуда деньги.'))
            offer.notice = Markup('').join(parts)

    @api.constrains('asset', 'network_id')
    def _check_network(self):
        for offer in self:
            allowed = ASSET_NETWORKS.get(offer.asset, ())
            if offer.network_id and offer.network_id.code not in allowed:
                raise ValidationError(_(
                    '%(asset)s не ходит в сети %(network)s. Перевод в чужую сеть '
                    'означает потерю средств.', asset=offer.asset, network=offer.network_id.name))

    @api.constrains('amount_min', 'amount_max', 'price')
    def _check_amounts(self):
        for offer in self:
            if offer.price <= 0:
                raise ValidationError(_('Цена должна быть больше нуля.'))
            if offer.amount_max <= 0 or offer.amount_min < 0 or offer.amount_min > offer.amount_max:
                raise ValidationError(_('Проверьте пределы: «от» не больше «до», оба больше нуля.'))

    @api.constrains('rub_bank', 'rub_sbp', 'rub_cash')
    def _check_methods(self):
        for offer in self:
            if not (offer.rub_bank or offer.rub_sbp or offer.rub_cash):
                raise ValidationError(_('Отметьте хотя бы один способ рублёвого расчёта.'))

    def action_pause(self):
        self.write({'state': 'paused'})

    def action_activate(self):
        self.write({'state': 'active'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_respond(self):
        self.ensure_one()
        if self.author_id == self.env.user.partner_id:
            raise UserError(_('Это ваше объявление.'))
        if self.state != 'active':
            raise UserError(_('Объявление не активно.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Обмен: %(name)s', name=self.name),
            'res_model': 'coop.crypto.respond',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_offer_id': self.id,
                        'default_amount': self.amount_min or self.amount_max},
        }

    # ── Панель фильтров каталога ───────────────────────────────────────

    def _coop_catalog_filters(self, domain):
        def choice(name):
            return [{'value': code, 'label': label}
                    for code, label in self._fields[name].selection]
        networks = self.env['coop.wallet.network'].sudo().search([('code', '!=', 'koop')])
        return [
            {'code': 'side', 'label': 'Продают или покупают', 'widget': 'select',
             'field': 'side', 'placeholder': 'Любое', 'options': choice('side')},
            {'code': 'asset', 'label': 'Цифровая валюта', 'widget': 'select',
             'field': 'asset', 'placeholder': 'Любая', 'options': choice('asset')},
            {'code': 'network', 'label': 'Сеть', 'widget': 'select',
             'field': 'network_id', 'placeholder': 'Любая',
             'options': [{'value': n.id, 'label': n.name} for n in networks]},
            {'code': 'city', 'label': 'Город', 'widget': 'text', 'field': 'city',
             'operator': 'ilike', 'placeholder': 'Для встречи с наличными'},
            {'code': 'price', 'label': 'Цена за единицу, ₽', 'widget': 'range', 'field': 'price'},
            {'code': 'quick', 'label': 'Быстрые фильтры', 'widget': 'quick', 'options': [
                {'value': 'sbp', 'label': '⚡ СБП', 'domain': [('rub_sbp', '=', True)]},
                {'value': 'cash', 'label': '💵 Наличные', 'domain': [('rub_cash', '=', True)]},
                {'value': 'trust', 'label': '🛡 Доверие от 75%',
                 'domain': [('author_id.coop_trust', '>=', 75)]},
            ]},
        ]


def _fmt(value):
    if not value:
        return '0'
    text = ('%.8f' % value).rstrip('0').rstrip('.')
    whole, _dot, frac = text.partition('.')
    whole = '{:,}'.format(int(whole)).replace(',', ' ')
    return whole + (',' + frac if frac else '')


class CoopCryptoTrade(models.Model):
    """Состоявшийся (или идущий) обмен — запись о факте, не расчёт.

    Стороны переводят друг другу сами: одна — цифровую валюту со своего
    кошелька, другая — рубли своим способом. Платформа фиксирует, о чём
    договорились и что обе подтвердили. Отменить может любая сторона до
    завершения; спор разбирает администратор.
    """
    _name = 'coop.crypto.trade'
    _description = 'Обмен цифровой валюты'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    number = fields.Char(string='Номер', readonly=True, copy=False)
    offer_id = fields.Many2one('coop.crypto.offer', string='Объявление', required=True,
                               index=True, ondelete='restrict')
    maker_id = fields.Many2one(related='offer_id.author_id', string='Автор объявления',
                               store=True, index=True)
    taker_id = fields.Many2one('res.partner', string='Откликнулся', required=True, index=True)
    side = fields.Selection(related='offer_id.side', store=True)
    asset = fields.Selection(related='offer_id.asset', store=True)
    network_id = fields.Many2one(related='offer_id.network_id', store=True)
    currency_id = fields.Many2one(related='offer_id.currency_id')
    amount = fields.Float(string='Сколько, единиц', digits=(16, 8), required=True)
    price = fields.Monetary(string='Цена за единицу, ₽', required=True)
    total = fields.Monetary(string='Сумма, ₽', compute='_compute_total', store=True)
    rub_method = fields.Selection([
        ('sbp', 'СБП'), ('bank', 'Перевод на счёт'), ('cash', 'Наличные при встрече'),
    ], string='Как платят рубли', required=True)
    date = fields.Datetime(string='Когда', default=fields.Datetime.now, required=True)
    maker_confirmed = fields.Boolean(string='Автор подтвердил', readonly=True)
    taker_confirmed = fields.Boolean(string='Откликнувшийся подтвердил', readonly=True)
    state = fields.Selection([
        ('agreed', 'Договорились'),
        ('rub_sent', 'Рубли отправлены'),
        ('done', 'Состоялся'),
        ('cancelled', 'Отменён'),
        ('disputed', 'Спор'),
    ], string='Состояние', default='agreed', required=True, index=True, tracking=True)
    is_mine = fields.Boolean(compute='_compute_is_mine', search='_search_is_mine')

    @api.depends('amount', 'price')
    def _compute_total(self):
        for trade in self:
            trade.total = (trade.amount or 0) * (trade.price or 0)

    def _compute_is_mine(self):
        me = self.env.user.partner_id
        for trade in self:
            trade.is_mine = me in (trade.maker_id | trade.taker_id)

    def _search_is_mine(self, operator, value):
        me = self.env.user.partner_id.id
        domain = ['|', ('maker_id', '=', me), ('taker_id', '=', me)]
        if operator != 'in':  # Odoo 19: признак — оператором in
            return NotImplemented
        return domain

    @api.model_create_multi
    def create(self, vals_list):
        trades = super().create(vals_list)
        for trade in trades.filtered(lambda t: not t.number):
            trade.number = 'ОБМ-%05d' % trade.id
        return trades

    def _my_side(self):
        me = self.env.user.partner_id
        if me == self.maker_id:
            return 'maker'
        if me == self.taker_id:
            return 'taker'
        raise UserError(_('Вы не сторона этого обмена.'))

    def action_rub_sent(self):
        for trade in self:
            trade._my_side()
            trade.state = 'rub_sent'

    def action_confirm(self):
        for trade in self:
            side = trade._my_side()
            trade['%s_confirmed' % side] = True
            if trade.maker_confirmed and trade.taker_confirmed:
                trade.state = 'done'

    def action_cancel(self):
        for trade in self:
            trade._my_side()
            if trade.state == 'done':
                raise UserError(_('Состоявшийся обмен не отменяется.'))
            trade.state = 'cancelled'

    def action_dispute(self):
        for trade in self:
            trade._my_side()
            trade.state = 'disputed'


class CoopCryptoRespond(models.TransientModel):
    _name = 'coop.crypto.respond'
    _description = 'Отклик на объявление об обмене'

    offer_id = fields.Many2one('coop.crypto.offer', required=True)
    asset = fields.Selection(related='offer_id.asset')
    currency_id = fields.Many2one(related='offer_id.currency_id')
    price = fields.Monetary(related='offer_id.price')
    amount = fields.Float(string='Сколько, единиц', digits=(16, 8), required=True)
    total = fields.Monetary(string='Сумма, ₽', compute='_compute_total')
    rub_method = fields.Selection([
        ('sbp', 'СБП'), ('bank', 'Перевод на счёт'), ('cash', 'Наличные при встрече'),
    ], string='Как платите рубли', required=True, default='sbp')
    notice = fields.Html(related='offer_id.notice')

    @api.depends('amount', 'price')
    def _compute_total(self):
        for wizard in self:
            wizard.total = (wizard.amount or 0) * (wizard.price or 0)

    def action_confirm(self):
        self.ensure_one()
        offer = self.offer_id
        if not (offer.amount_min <= self.amount <= offer.amount_max):
            raise UserError(_('Объявление принимает от %(a)s до %(b)s %(asset)s.',
                              a=_fmt(offer.amount_min), b=_fmt(offer.amount_max),
                              asset=offer.asset))
        allowed = {'sbp': offer.rub_sbp, 'bank': offer.rub_bank, 'cash': offer.rub_cash}
        if not allowed.get(self.rub_method):
            raise UserError(_('Автор объявления не принимает этот способ.'))
        trade = self.env['coop.crypto.trade'].sudo().create({
            'offer_id': offer.id,
            'taker_id': self.env.user.partner_id.id,
            'amount': self.amount,
            'price': offer.price,
            'rub_method': self.rub_method,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.crypto.trade',
            'res_id': trade.id,
            'view_mode': 'form',
            'target': 'current',
        }

# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CoopTokenClaim(models.Model):
    """Выпуск токенов требования на ресурс.

    Фермер весной знает, что осенью будет двадцать тонн моркови, а деньги
    на посевную нужны сейчас. Он публикует объявление и тем же движением
    выпускает токены: один токен — один килограмм моркови первого сорта,
    во Владивостоке, до первого октября. Покупатель платит сегодня и
    получает право забрать товар в срок; до срока он волен перепродать
    это право кому угодно из участников.

    Четыре обязательных признака требования — что, какого качества, где и
    к какому сроку — не украшение карточки, а само содержание токена. Без
    любого из них токен превращается в обещание вообще, а обещание вообще
    ничем не обеспечено и ничего не стоит.

    **Обеспечение — деньги покупателя в эскроу, а не слово продавца.**
    Оплата блокируется смарт-контрактом и уходит поставщику только после
    двусторонней приёмки. Прошёл срок, поставки нет — контракт возвращает
    деньги сам, без заявления, без разбирательства и без участия
    платформы. Это единственная часть конструкции, которая работает даже
    если платформа завтра выключится.

    **Токен — Jetton (TEP-74), делимый.** Один выпуск — один
    jetton-master, эмиссия равна количеству единиц. Делимость нужна не для
    красоты: покупателю может понадобиться две тонны из двадцати, а
    держателю — продать половину. Неделимый NFT заставил бы торговать
    партией целиком.

    Ключи у участника: платформа готовит параметры транзакции, подписывает
    её кошелёк владельца через TON Connect. Хранить чужие ключи — значит
    стать хранителем чужого имущества со всеми вытекающими, и мы этого не
    делаем.
    """
    _name = 'coop.token.claim'
    _description = 'Выпуск токенов требования'
    _inherit = ['mail.thread']
    _order = 'delivery_date, id desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=True)

    # ── Что обещано ──────────────────────────────────────────────────────
    resource_id = fields.Many2one(
        'coop.resource', string='Объявление', required=True, index=True,
        ondelete='cascade',
        help='Публикация ресурса, из которой выпущены токены. Выпуск не '
             'существует сам по себе: он всегда обещание по конкретному '
             'объявлению.')
    issuer_id = fields.Many2one(
        'res.partner', string='Поставщик', required=True, index=True,
        help='Кто обязан поставить. Он же владелец jetton-мастера.')

    quantity = fields.Float(
        string='Количество', required=True, digits=(16, 3),
        help='Сколько единиц обещано. Столько же токенов и выпускается: '
             'один токен — одна единица.')
    unit_label = fields.Char(
        string='Единица', required=True, default='кг',
        help='Килограмм, тонна, штука, час, сутки. Как в объявлении.')

    quality = fields.Char(
        string='Качество', required=True,
        help='«Морковь столовая, первый сорт, ГОСТ 32284-2013». Без этого '
             'спор о том, то ли привезли, решать нечем.')
    delivery_place = fields.Char(
        string='Место передачи', required=True,
        help='Город и адрес, где товар передаётся. «Владивосток, склад на '
             'Русской 2» — а не просто «Владивосток».')
    delivery_date = fields.Date(
        string='Срок поставки', required=True, index=True,
        help='После этой даты неисполненный выпуск даёт держателям право '
             'забрать деньги из эскроу.')

    is_future = fields.Boolean(
        string='Товара ещё нет', default=True,
        help='Урожай, который вырастет; работа, которая будет сделана. '
             'Покупатель видит это на витрине и подтверждает отдельно: '
             'риск он берёт осознанно, а не по невнимательности.')

    # ── Цена ─────────────────────────────────────────────────────────────
    #
    # Цену назначает поставщик, и она неизменна после выпуска. Торг
    # начинается дальше, на вторичном рынке между держателями, — там цена
    # и покажет, чего обещание стоит на самом деле.
    price_per_unit = fields.Float(
        string='Цена за единицу', required=True, digits=(16, 4),
        help='В валюте расчёта. Меняется только до выпуска.')
    settlement_currency = fields.Selection([
        ('usdt', 'USDT'),
        ('rub', 'Рублёвый токен'),
        ('ton', 'TON'),
    ], string='Валюта расчёта', default='usdt', required=True,
        help='Расчёт в USDT: рублёвого токена в сети TON пока нет, а курс '
             'TON за время до поставки может уйти вдвое в любую сторону — '
             'эскроу тогда вернул бы не то, что положили.')
    total_price = fields.Float(
        string='Стоимость выпуска', compute='_compute_total_price', store=True,
        digits=(16, 4))

    # ── Состояние ────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Черновик'),
        ('minted', 'Выпущены'),
        ('trading', 'Торгуются'),
        ('delivering', 'Идёт поставка'),
        ('settled', 'Исполнено'),
        ('defaulted', 'Сорвано'),
        ('cancelled', 'Отменено'),
    ], string='Состояние', default='draft', required=True, index=True,
        tracking=True)

    # ── Сеть TON ─────────────────────────────────────────────────────────
    #
    # Адреса хранятся строками, а не ссылками: узел сети — источник
    # истины, база лишь помнит, где смотреть. Если адрес пуст, значит
    # выпуск ещё не доехал до сети, и это видно без догадок.
    jetton_master_address = fields.Char(
        string='Адрес jetton-мастера', readonly=True, copy=False, index=True,
        help='Контракт выпуска в сети TON. Пока пусто — токенов в сети нет.')
    escrow_address = fields.Char(
        string='Адрес эскроу', readonly=True, copy=False,
        help='Контракт, где лежат деньги покупателей до приёмки.')
    mint_tx_hash = fields.Char(string='Транзакция выпуска', readonly=True, copy=False)
    network = fields.Selection([
        ('testnet', 'Тестовая сеть'),
        ('mainnet', 'Основная сеть'),
    ], string='Сеть', default='testnet', required=True, readonly=True)

    # ── Исполнение ───────────────────────────────────────────────────────
    delivered_quantity = fields.Float(
        string='Поставлено', digits=(16, 3), readonly=True,
        help='Сколько единиц принято держателями. Частичная поставка — '
             'нормальный исход: держатель решает при приёмке, берёт он '
             'привезённое или отказывается.')
    settled_on = fields.Date(string='Исполнено', readonly=True)
    default_reason = fields.Char(string='Почему сорвано', readonly=True)

    order_ids = fields.One2many('coop.token.order', 'claim_id', string='Заявки')
    holder_ids = fields.One2many('coop.token.holding', 'claim_id', string='Держатели')
    holder_count = fields.Integer(compute='_compute_holder_count', string='Держателей')

    available_quantity = fields.Float(
        string='Свободно у поставщика', compute='_compute_available', store=True,
        digits=(16, 3), help='Сколько единиц ещё не продано.')

    import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    _quantity_positive = models.Constraint(
        'check(quantity > 0)',
        'Выпуск на ноль единиц не имеет смысла.',
    )
    _price_positive = models.Constraint(
        'check(price_per_unit > 0)',
        'Цена за единицу должна быть больше нуля.',
    )

    @api.depends('resource_id.name', 'quantity', 'unit_label', 'delivery_date')
    def _compute_display_name(self):
        for record in self:
            record.display_name = '%s — %g %s до %s' % (
                record.resource_id.name or _('Без объявления'),
                record.quantity,
                record.unit_label or '',
                record.delivery_date and record.delivery_date.strftime('%d.%m.%Y') or '—',
            )

    @api.depends('quantity', 'price_per_unit')
    def _compute_total_price(self):
        for record in self:
            record.total_price = record.quantity * record.price_per_unit

    @api.depends('holder_ids.quantity', 'quantity')
    def _compute_available(self):
        for record in self:
            sold = sum(record.holder_ids.mapped('quantity'))
            record.available_quantity = record.quantity - sold

    @api.depends('holder_ids')
    def _compute_holder_count(self):
        for record in self:
            record.holder_count = len(record.holder_ids.filtered(
                lambda h: h.quantity > 0))

    @api.constrains('delivery_date')
    def _check_delivery_date(self):
        for record in self:
            if record.state == 'draft' and record.delivery_date < fields.Date.context_today(record):
                raise ValidationError(_(
                    'Срок поставки уже прошёл. Выпустить токены задним '
                    'числом нельзя: держателю нечего было бы ждать.'))

    def action_mint(self):
        """Выпустить токены в сеть.

        Проверка эмитента здесь, а не на форме: выпускать вправе только
        участник с подтверждённой личностью. За токеном стоит обещание
        поставить товар, и если обещавшего нельзя опознать, обещание не
        стоит ничего — а на витрине оно выглядело бы так же, как честное.
        """
        for record in self:
            if not record.issuer_id.coop_verified:
                raise UserError(_(
                    'Выпускать токены может только участник с '
                    'подтверждённой личностью. За токеном стоит обещание '
                    'поставить товар — должно быть видно, с кого спрашивать.'))
            if not record.issuer_id.coop_ton_address:
                raise UserError(_(
                    'У поставщика не подключён кошелёк TON. Выпуск '
                    'подписывается его кошельком: платформа чужих ключей '
                    'не хранит.'))
            record.state = 'minted'
        return True

    def action_start_trading(self):
        self.filtered(lambda r: r.state == 'minted').write({'state': 'trading'})
        return True

    def action_settle(self):
        """Отметить выпуск исполненным.

        Ставится не по сроку, а по приёмкам: пока хоть один держатель ждёт
        товар, выпуск не исполнен, сколько бы дат ни прошло.
        """
        for record in self:
            waiting = record.holder_ids.filtered(lambda h: h.quantity > 0)
            if waiting:
                raise UserError(_(
                    'Ещё %s держателей не приняли товар. Пока они ждут, '
                    'выпуск не исполнен.') % len(waiting))
            record.write({
                'state': 'settled',
                'settled_on': fields.Date.context_today(record),
            })
        return True

    def action_default(self):
        """Признать выпуск сорванным.

        Три последствия сразу, и все три обязательны: деньги держателей
        возвращаются из эскроу, поставщику списывается доверие, сверх
        возврата удерживается штраф. Одно списание доверия ничего не
        возмещает тому, кто остался без товара и без денег до срока.
        """
        for record in self:
            record.write({
                'state': 'defaulted',
                'default_reason': record.default_reason or _(
                    'Срок поставки прошёл, товар не передан'),
            })
            record.issuer_id.message_post(body=_(
                'Сорван выпуск токенов: %s. Деньги держателей возвращаются '
                'из эскроу.') % record.display_name)
        return True

    def action_cancel(self):
        for record in self:
            if record.holder_ids.filtered(lambda h: h.quantity > 0):
                raise UserError(_(
                    'У выпуска есть держатели. Отменить его — значит '
                    'отобрать у них купленное; здесь только срыв с '
                    'возвратом денег.'))
            record.state = 'cancelled'
        return True


class CoopTokenHolding(models.Model):
    """Сколько токенов выпуска у кого на руках.

    Зеркало балансов из сети, а не источник истины: истина в jetton-
    кошельках на TON, здесь — то, что платформа о них знает. Нужно затем,
    чтобы показывать витрину и держателей, не спрашивая сеть на каждый
    чих, и чтобы было с чем сверяться, когда сеть ответит иначе.
    """
    _name = 'coop.token.holding'
    _description = 'Токены выпуска на руках'
    _order = 'quantity desc, id'

    claim_id = fields.Many2one(
        'coop.token.claim', string='Выпуск', required=True, index=True,
        ondelete='cascade')
    partner_id = fields.Many2one(
        'res.partner', string='Держатель', required=True, index=True)
    quantity = fields.Float(string='Токенов', digits=(16, 3), required=True)
    acquired_on = fields.Datetime(string='Куплено', default=fields.Datetime.now)
    accepted_quantity = fields.Float(
        string='Принято', digits=(16, 3),
        help='Сколько единиц держатель принял по приёмке. Остаток либо '
             'ещё ждёт поставки, либо вернулся деньгами.')

    _one_holding_per_partner = models.Constraint(
        'unique(claim_id, partner_id)',
        'У держателя одна запись на выпуск: количество меняется, записей '
        'не прибавляется.',
    )

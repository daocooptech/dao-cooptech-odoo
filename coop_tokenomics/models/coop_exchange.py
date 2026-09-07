# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopExchange(models.AbstractModel):
    """Данные торгового экрана одним запросом.

    Экран биржи показывает сразу пять вещей: список рынков, заявки на
    продажу и на покупку по выбранному, последние сделки и состояние
    кошелька. Собирать их пятью запросами значит показывать участнику
    рынок, собранный из пяти разных моментов времени: за те доли секунды,
    что идут ответы, чужая сделка успевает пройти, и цена в списке уже не
    та, что в стакане.

    Поэтому один вызов и один снимок. Это не оптимизация ради скорости —
    на бирже несогласованные цифры хуже медленных.
    """
    _name = 'coop.exchange'
    _description = 'Биржа токенов: данные экрана'

    # ── Рынки ────────────────────────────────────────────────────────────

    @api.model
    def markets(self, limit=60):
        """Список торгуемых выпусков с ценой и оборотом.

        Рынок здесь — один выпуск токенов: партия товара определённого
        качества, в определённом месте, к определённому сроку. Пара на
        обычной бирже устроена так же — «это за то», — только «то» у нас
        всегда валюта расчёта, потому что менять морковь на пиломатериалы
        напрямую значит заводить пул ликвидности на каждую пару, которого
        никто не наполнит.
        """
        Claim = self.env['coop.token.claim']
        claims = Claim.search(
            [('state', 'in', ('trading', 'delivering', 'minted'))],
            order='delivery_date', limit=limit)

        Order = self.env['coop.token.order']
        Trade = self.env['coop.token.trade']
        result = []
        for claim in claims:
            open_orders = Order.search([
                ('claim_id', '=', claim.id),
                ('state', 'in', ('open', 'partial')),
            ])
            sells = open_orders.filtered(lambda o: o.side == 'sell')
            buys = open_orders.filtered(lambda o: o.side == 'buy')
            trades = Trade.search([
                ('claim_id', '=', claim.id), ('state', '=', 'done')],
                order='confirmed_on desc', limit=20)

            # Цена рынка — по последней прошедшей сделке, а при её
            # отсутствии по лучшему предложению на продажу. Не средняя:
            # средняя между «продам за сто» и «куплю за пятьдесят» —
            # число, по которому никто не торговал и не будет.
            last = trades[:1].price_per_unit if trades else 0.0
            best_ask = min(sells.mapped('price_per_unit')) if sells else 0.0
            best_bid = max(buys.mapped('price_per_unit')) if buys else 0.0
            price = last or best_ask or claim.price_per_unit

            result.append({
                'id': claim.id,
                'name': claim.resource_id.name or claim.display_name,
                'issuer': claim.issuer_id.name,
                'quality': claim.quality,
                'place': claim.delivery_place,
                'due': claim.delivery_date and claim.delivery_date.isoformat(),
                'unit': claim.unit_label,
                'currency': claim.settlement_currency,
                'issue_price': claim.price_per_unit,
                'price': price,
                'best_ask': best_ask,
                'best_bid': best_bid,
                # Изменение к цене выпуска — то, что на бирже называют
                # «сколько прибавил с размещения». Считается от цены
                # выпуска, а не от вчерашней: сделок по большинству
                # выпусков за сутки просто нет.
                'change': ((price - claim.price_per_unit) / claim.price_per_unit * 100
                           if claim.price_per_unit else 0.0),
                'supply': claim.quantity,
                'available': claim.available_quantity,
                'holders': claim.holder_count,
                'volume': sum(trades.mapped('total_price')),
                'trades': len(trades),
                'state': claim.state,
                'is_future': claim.is_future,
            })
        return result

    # ── Стакан и сделки ──────────────────────────────────────────────────

    @api.model
    def book(self, claim_id):
        """Заявки по выпуску: продажи, покупки, последние сделки.

        Две колонки, как в биржевом стакане, — но сводятся они не сами.
        Участник выбирает заявку и жмёт «купить»; автоматическое сведение
        встречных заявок по цене и есть организованные торги, на которые
        нужна лицензия. Внешне разница невелика, юридически — принципиальна.
        """
        claim = self.env['coop.token.claim'].browse(claim_id)
        if not claim.exists():
            return {}
        Order = self.env['coop.token.order']
        me = self.env.user._coop_acting_partner()

        def row(order):
            return {
                'id': order.id,
                'price': order.price_per_unit,
                'quantity': order.quantity_left or order.quantity,
                'total': (order.quantity_left or order.quantity) * order.price_per_unit,
                'partner': order.partner_id.name,
                'partner_id': order.partner_id.id,
                'kind': order.kind,
                'premium': order.premium_percent,
                'mine': order.partner_id.id == me.id,
            }

        sells = Order.search([
            ('claim_id', '=', claim_id), ('side', '=', 'sell'),
            ('state', 'in', ('open', 'partial')),
        ], order='price_per_unit')
        buys = Order.search([
            ('claim_id', '=', claim_id), ('side', '=', 'buy'),
            ('state', 'in', ('open', 'partial')),
        ], order='price_per_unit desc')
        trades = self.env['coop.token.trade'].search([
            ('claim_id', '=', claim_id), ('state', '=', 'done'),
        ], order='confirmed_on desc', limit=25)

        holding = claim.holder_ids.filtered(lambda h: h.partner_id == me)
        return {
            'claim': {
                'id': claim.id,
                'name': claim.resource_id.name or claim.display_name,
                'issuer': claim.issuer_id.name,
                'quality': claim.quality,
                'place': claim.delivery_place,
                'due': claim.delivery_date and claim.delivery_date.isoformat(),
                'unit': claim.unit_label,
                'currency': claim.settlement_currency,
                'issue_price': claim.price_per_unit,
                'supply': claim.quantity,
                'available': claim.available_quantity,
                'deposit': claim.deposit_amount,
                'deposit_paid': claim.deposit_paid,
                'state': claim.state,
                'is_future': claim.is_future,
                'jetton': claim.jetton_master_address,
                'escrow': claim.escrow_address,
                'network': claim.network,
            },
            'asks': [row(o) for o in sells],
            'bids': [row(o) for o in buys],
            'trades': [{
                'price': t.price_per_unit,
                'quantity': t.quantity,
                'total': t.total_price,
                'when': t.confirmed_on and fields.Datetime.to_string(t.confirmed_on),
                'buyer': t.buyer_id.name,
                'seller': t.seller_id.name,
                'tx': t.tx_hash,
            } for t in trades],
            'my_holding': holding[:1].quantity if holding else 0.0,
        }

    # ── Кошелёк ──────────────────────────────────────────────────────────

    @api.model
    def wallet(self):
        """Что показывать в шапке терминала.

        Кошелёк не подключён — это не ошибка и не пустое место: покупать
        и продавать нельзя, и участник должен видеть причину сразу, а не
        после нажатия кнопки.
        """
        me = self.env.user._coop_acting_partner()
        holdings = self.env['coop.token.holding'].search([('partner_id', '=', me.id)])
        return {
            'partner': me.name,
            'address': me.coop_ton_address or '',
            'network': me.coop_ton_network or '',
            'connected': bool(me.coop_ton_address),
            'positions': len(holdings.filtered(lambda h: h.quantity > 0)),
            'my_claims': self.env['coop.token.claim'].search_count([
                ('issuer_id', '=', me.id)]),
        }

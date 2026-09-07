# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models

# Категории над списком рынков — то же, что на биржах вкладки «Тренд»,
# «Новые», «Растущие», только переведённое на товар. Понятие «тренда» у
# нас заменяет срок: чем ближе поставка, тем горячее торгуют, потому что
# ждать осталось меньше и обещание превращается в товар.
CATEGORIES = ['all', 'soon', 'new', 'up', 'down']

# По чему группировать. Четыре разреза, и каждый отвечает на свой вопрос:
# что покупаю, когда получу, куда ехать, у кого беру.
GROUPINGS = ['none', 'type', 'due', 'place', 'issuer']

TYPE_LABELS = {
    'material': 'Материалы',
    'equipment': 'Оборудование',
    'labour': 'Труд',
    'financial': 'Финансы',
}


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
    def markets(self, category='all', grouping='none', limit=200):
        """Список торгуемых выпусков с ценой, оборотом и оценкой.

        Рынок здесь — один выпуск токенов: партия товара определённого
        качества, в определённом месте, к определённому сроку. Пара на
        обычной бирже устроена так же — «это за то», — только «то» у нас
        всегда валюта расчёта: менять морковь на пиломатериалы напрямую
        значит заводить пул ликвидности на каждую пару, которого никто не
        наполнит.
        """
        Claim = self.env['coop.token.claim']
        claims = Claim.search(
            [('state', 'in', ('trading', 'delivering', 'minted'))],
            order='delivery_date', limit=limit)

        Order = self.env['coop.token.order']
        Trade = self.env['coop.token.trade']
        today = fields.Date.context_today(self)
        me = self.env.user._coop_acting_partner()

        rows = []
        for claim in claims:
            open_orders = Order.search([
                ('claim_id', '=', claim.id),
                ('state', 'in', ('open', 'partial')),
            ])
            sells = open_orders.filtered(lambda o: o.side == 'sell')
            buys = open_orders.filtered(lambda o: o.side == 'buy')
            trades = Trade.search([
                ('claim_id', '=', claim.id), ('state', '=', 'done')],
                order='confirmed_on desc', limit=30)

            # Цена рынка — по последней прошедшей сделке, а при её
            # отсутствии по лучшему предложению на продажу. Не средняя:
            # средняя между «продам за сто» и «куплю за пятьдесят» — число,
            # по которому никто не торговал и не будет.
            last = trades[:1].price_per_unit if trades else 0.0
            best_ask = min(sells.mapped('price_per_unit')) if sells else 0.0
            best_bid = max(buys.mapped('price_per_unit')) if buys else 0.0
            price = last or best_ask or claim.price_per_unit
            change = ((price - claim.price_per_unit) / claim.price_per_unit * 100
                      if claim.price_per_unit else 0.0)

            days_left = (claim.delivery_date - today).days if claim.delivery_date else 999
            age_days = (fields.Date.to_date(claim.create_date) - today).days * -1 \
                if claim.create_date else 999

            rows.append({
                'id': claim.id,
                'name': claim.resource_id.name or claim.display_name,
                'issuer': claim.issuer_id.name,
                'issuer_id': claim.issuer_id.id,
                'type': claim.resource_id.resource_type or 'material',
                'type_label': TYPE_LABELS.get(
                    claim.resource_id.resource_type or 'material', 'Прочее'),
                'quality': claim.quality,
                'place': claim.delivery_place,
                'city': (claim.resource_id.city or '').strip() or '—',
                'due': claim.delivery_date and claim.delivery_date.isoformat(),
                'days_left': days_left,
                'age_days': age_days,
                'unit': claim.unit_label,
                'currency': claim.settlement_currency,
                'issue_price': claim.price_per_unit,
                'price': price,
                'best_ask': best_ask,
                'best_bid': best_bid,
                'change': change,
                'supply': claim.quantity,
                'available': claim.available_quantity,
                'holders': claim.holder_count,
                'volume': sum(trades.mapped('total_price')),
                'trades': len(trades),
                'state': claim.state,
                'is_future': claim.is_future,
                'mine': claim.issuer_id.id == me.id,
                'spark': list(reversed(trades.mapped('price_per_unit')))[-12:],
            })
            rows[-1].update(self._reliability(claim, rows[-1]))

        # Счётчики считаются по всему набору, а не по отфильтрованному:
        # иначе на вкладке «Скоро поставка» в подписи «Все рынки» стоит
        # число самой этой вкладки, и переключаться становится некуда.
        counts = self._counts(rows)
        rows = self._filter_category(rows, category)
        return {
            'rows': rows,
            'groups': self._group(rows, grouping),
            'grouping': grouping,
            'category': category,
            'counts': counts,
        }

    def _filter_category(self, rows, category):
        """Категории — не украшение, а ответ на «что смотреть сначала».

        «Скоро поставка» вместо биржевого «тренда»: у обещания на товар
        нет разогрева новостями, зато есть срок, и по мере его
        приближения торгуют чаще. «Новые выпуски» — прямой аналог новых
        пар. «Дорожают» и «дешевеют» — Gainers и Losers, только считанные
        от цены выпуска, а не от вчерашней: сделок по большинству
        выпусков за сутки просто нет.
        """
        if category == 'soon':
            return [r for r in rows if 0 <= r['days_left'] <= 30]
        if category == 'new':
            return [r for r in rows if r['age_days'] <= 14]
        if category == 'up':
            return sorted([r for r in rows if r['change'] > 0],
                          key=lambda r: -r['change'])
        if category == 'down':
            return sorted([r for r in rows if r['change'] < 0],
                          key=lambda r: r['change'])
        return rows

    def _group(self, rows, grouping):
        """Разложить рынки по группам с итогами по каждой.

        Итог по группе — оборот и число рынков: без них группировка
        превращается в оглавление, по которому не видно, где вообще
        что-то происходит.
        """
        if grouping == 'none':
            return []
        keys = {
            'type': lambda r: (r['type'], r['type_label']),
            'due': lambda r: self._due_bucket(r['days_left']),
            'place': lambda r: (r['city'], r['city']),
            'issuer': lambda r: (str(r['issuer_id']), r['issuer']),
        }
        pick = keys.get(grouping)
        if not pick:
            return []
        buckets = {}
        for row in rows:
            key, label = pick(row)
            bucket = buckets.setdefault(key, {
                'key': key, 'label': label, 'ids': [], 'volume': 0.0, 'count': 0,
            })
            bucket['ids'].append(row['id'])
            bucket['volume'] += row['volume']
            bucket['count'] += 1
        return sorted(buckets.values(), key=lambda b: -b['count'])

    def _due_bucket(self, days):
        if days < 0:
            return ('overdue', 'Срок прошёл')
        if days <= 30:
            return ('m1', 'В ближайший месяц')
        if days <= 90:
            return ('m3', 'В ближайший квартал')
        if days <= 180:
            return ('m6', 'В полугодие')
        return ('later', 'Позже')

    def _counts(self, rows):
        """Сколько рынков в каждой категории — для подписей на вкладках."""
        return {
            'all': len(rows),
            'soon': len([r for r in rows if 0 <= r['days_left'] <= 30]),
            'new': len([r for r in rows if r['age_days'] <= 14]),
            'up': len([r for r in rows if r['change'] > 0]),
            'down': len([r for r in rows if r['change'] < 0]),
        }

    def _reliability(self, claim, row):
        """Оценка выпуска: чем обеспечено обещание и как его исполняют.

        Устроена как сводные оценки токенов на биржах — из держателей,
        оборота и ликвидности, — но собрана из того, что на платформе
        действительно что-то значит: уровень доверия поставщика, внесённый
        залог, история его прошлых выпусков и живость торгов.

        **Показывается с расшифровкой, а не одной цифрой.** Балл без
        объяснения — это просьба поверить платформе на слово; участнику
        нужно видеть, что именно за ним стоит, чтобы решать самому.
        Поэтому наружу уходит и число, и четыре слагаемых.

        Максимум сорок, потому что слагаемых четыре и каждое до десяти;
        приводить к ста незачем — точности это не добавит, а видимость
        точности создаст.
        """
        issuer = claim.issuer_id
        # Доверие поставщика — уже посчитанное платформой по завершённым
        # сделкам. Своей формулы здесь не заводим: две меры доверия рядом
        # неизбежно разойдутся, и участник не поймёт, какой верить.
        trust = min((issuer.coop_trust or 0) / 10.0, 10.0)

        deposit = 10.0 if claim.deposit_paid else 0.0

        history = self.env['coop.token.claim'].search([
            ('issuer_id', '=', issuer.id),
            ('state', 'in', ('settled', 'defaulted')),
        ])
        settled = len(history.filtered(lambda c: c.state == 'settled'))
        broken = len(history.filtered(lambda c: c.state == 'defaulted'))
        if settled or broken:
            record = settled / float(settled + broken) * 10.0
        else:
            # Первый выпуск — не плохой и не хороший: половина балла и
            # прямая пометка, что истории ещё нет.
            record = 5.0

        liveliness = min(row['holders'] * 1.5 + row['trades'] * 0.8, 10.0)

        return {
            'score': round(trust + deposit + record + liveliness, 1),
            'score_parts': {
                'trust': round(trust, 1),
                'deposit': deposit,
                'record': round(record, 1),
                'liveliness': round(liveliness, 1),
            },
            'issuer_trust': issuer.coop_trust or 0,
            'issuer_settled': settled,
            'issuer_broken': broken,
            'first_issue': not (settled or broken),
        }

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
        ], order='confirmed_on desc', limit=40)

        holding = claim.holder_ids.filtered(lambda h: h.partner_id == me)

        # Линия цены строится по сделкам в хронологическом порядке. Свечей
        # нет намеренно: по большинству выпусков сделок единицы, и свечной
        # график рисовал бы движение, которого не было.
        chart = [{
            'price': t.price_per_unit,
            'when': t.confirmed_on and fields.Datetime.to_string(t.confirmed_on),
        } for t in reversed(trades)]

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
            'chart': chart,
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

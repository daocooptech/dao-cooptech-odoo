# -*- coding: utf-8 -*-
"""Биржа токенов: выпуски требований, заявки, сделки, доли в проектах.

Наполняется из уже существующих объявлений о ресурсах: токен требования
не бывает сам по себе, он всегда обещание по конкретной публикации. Берём
предложения (не спрос) от верифицированных участников — выпускать вправе
только тот, чью личность подтвердили.

Разброс намеренный: часть выпусков только что размещена, часть уже
торгуется с наценкой, по части идёт поставка, единицы сорваны. Каталог,
где всё в одном состоянии, не показывает ни фильтров, ни того, как экран
ведёт себя, когда что-то пошло не так.
"""
import logging
import random

from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

TARGET_CLAIMS = 120

# Качество — то, чем спор о «том ли привезли» решается без крика.
QUALITY_BY_TYPE = {
    'material': [
        'Первый сорт, ГОСТ 32284-2013',
        'Высший сорт, влажность до 14%',
        'Второй сорт, допускается калибр от 40 мм',
        'Сортировка по калибру 60–90 мм, без механических повреждений',
    ],
    'equipment': [
        'Исправное, наработка до 400 моточасов',
        'После планового ТО, с паспортом и отметками',
        'Рабочее состояние, косметические дефекты корпуса',
    ],
    'labour': [
        'Разряд не ниже четвёртого, с допуском',
        'Смена 8 часов, инструмент исполнителя',
        'С опытом от трёх лет, работа по акту',
    ],
    'financial': [
        'Возврат по графику, без досрочного истребования',
        'Единым платежом в срок',
    ],
}

UNIT_BY_TYPE = {
    'material': ['кг', 'т', 'м³', 'шт.'],
    'equipment': ['смена', 'сутки', 'моточас'],
    'labour': ['час', 'смена', 'нормо-час'],
    'financial': ['руб.'],
}

PLACES = [
    'склад на Русской, 2', 'логистический центр на Объездной',
    'производственная площадка, ул. Заводская, 14',
    'самовывоз с фермы', 'пункт выдачи кооператива',
    'склад временного хранения, терминал 3',
]

# Состояния в тех долях, в каких они встречаются: большая часть висит и
# торгуется, поставка идёт у меньшинства, срывов единицы — иначе биржа
# выглядела бы местом, где всех обманывают.
STATES = (
    ['trading'] * 52 + ['minted'] * 22 + ['delivering'] * 12
    + ['settled'] * 8 + ['draft'] * 4 + ['defaulted'] * 2
)


def load_tokens(env, target=TARGET_CLAIMS):
    Claim = env['coop.token.claim'].sudo()
    Order = env['coop.token.order'].sudo()
    Holding = env['coop.token.holding'].sudo()
    Resource = env['coop.resource'].sudo()
    Partner = env['res.partner'].sudo()

    rnd = random.Random(20260906)
    today = fields.Date.context_today(Claim)

    resources = Resource.search([
        ('state', '=', 'published'),
        ('listing_type', '=', 'offer'),
        ('owner_id.coop_verified', '=', True),
    ], order='id')
    if not resources:
        _logger.warning('Нет объявлений верифицированных участников — биржу не наполняю')
        return

    buyers = Partner.search([
        ('coop_is_participant', '=', True), ('coop_verified', '=', True)], order='id')

    _connect_wallets(Partner, resources.mapped('owner_id') | buyers[:80], rnd)

    created = skipped = 0
    claims = Claim.browse()
    # По одному объявлению бывает несколько выпусков: партия к осени и
    # партия к весне — это разные требования с разными сроками, и на
    # бирже они живут порознь. Проходим каталог дважды, второй раз — с
    # другими сроками; так набирается объём каталога, не выдумывая
    # объявлений, которых у участников нет.
    plan = [(resource, wave) for wave in (0, 1) for resource in resources]
    for index, (resource, wave) in enumerate(plan):
        if created >= target:
            break
        key = 'tokens#%s.%s' % (resource.id, wave)
        existing = Claim.search([('import_key', '=', key)], limit=1)
        if existing:
            skipped += 1
            claims |= existing
            continue

        rtype = resource.resource_type or 'material'
        unit = rnd.choice(UNIT_BY_TYPE.get(rtype, ['шт.']))
        quality = rnd.choice(QUALITY_BY_TYPE.get(rtype, ['По договорённости сторон']))
        quantity = float(rnd.choice([
            50, 100, 200, 500, 1000, 2000, 5000, 10, 20, 8, 12, 40]))
        # Цена ресурса ведётся в рублях, и цена обещания на него — тоже:
        # деление на условный курс давало числа, несопоставимые с
        # ценой того же товара в каталоге.
        price = round(max(resource.price or rnd.uniform(500, 9000), 100), 2)
        # Состояние берётся жребием, а не по порядку: при выборке
        # короче списка состояний срез приходился бы на первые два, и
        # весь разброс пропадал — ровно это и случилось в первый прогон.
        state = rnd.choice(STATES)
        delivery = today + timedelta(
            days=rnd.randint(14, 90) if wave == 0 else rnd.randint(120, 300))

        claim = Claim.create({
            'resource_id': resource.id,
            'issuer_id': resource.owner_id.id,
            'quantity': quantity,
            'unit_label': unit,
            'quality': quality,
            'delivery_place': '%s, %s' % (
                resource.city or 'Москва', rnd.choice(PLACES)),
            'delivery_date': delivery,
            'is_future': rnd.random() < 0.7,
            'price_per_unit': price,
            'settlement_currency': 'rub',
            'state': 'draft',
            'import_key': key,
        })
        # Залог вносится при размещении — до выпуска, а не после: иначе
        # между обещанием на витрине и обеспечением остаётся окно.
        claim.action_pay_deposit()
        if state != 'draft':
            claim.write({
                'state': state,
                'jetton_master_address': _fake_address(rnd),
                'escrow_address': _fake_address(rnd),
                'mint_tx_hash': _fake_hash(rnd),
            })
        if state == 'settled':
            claim.write({
                'settled_on': today - timedelta(days=rnd.randint(1, 60)),
                'deposit_returned': True,
                'delivered_quantity': quantity,
            })
        if state == 'defaulted':
            claim.write({
                'default_reason': 'Срок поставки прошёл, товар не передан',
            })
        claims |= claim
        created += 1

    _spread_created(env, claims, rnd)
    _ensure_defaults(Claim, claims, today)
    _make_orders_and_holdings(Order, Holding, claims, buyers, rnd, today)
    _make_trades(env, claims, rnd)
    _seed_owner(env, claims, rnd)
    _grant_project_shares(env)

    _logger.info('Биржа токенов: выпусков создано %s, пропущено %s', created, skipped)


def _make_trades(env, claims, rnd):
    """Прошедшие сделки: без них у биржи нет цены.

    Цена рынка берётся по последней сделке, а не по средней между «продам
    за сто» и «куплю за пятьдесят»: среднее — число, по которому никто не
    торговал и не будет. Пока сделок нет вовсе, показывать нечего, и
    терминал выглядит пустым при полном стакане.

    Цены расходятся вокруг цены выпуска в обе стороны: обещание к сроку
    то дорожает, то дешевеет, и ровный рост выглядел бы нарисованным.
    """
    Trade = env['coop.token.trade'].sudo()
    Holding = env['coop.token.holding'].sudo()
    for claim in claims.filtered(lambda c: c.state in ('trading', 'delivering')):
        if Trade.search_count([('claim_id', '=', claim.id)]):
            continue
        holders = claim.holder_ids.filtered(lambda h: h.quantity > 0)
        orders = claim.order_ids.filtered(lambda o: o.kind == 'primary')
        if not holders or not orders:
            continue
        for holder in holders:
            if rnd.random() > 0.75:
                continue
            price = round(claim.price_per_unit * rnd.uniform(0.88, 1.28), 4)
            quantity = round(holder.quantity * rnd.uniform(0.2, 1.0), 1) or holder.quantity
            Trade.create({
                'order_id': orders[0].id,
                'claim_id': claim.id,
                'seller_id': claim.issuer_id.id,
                'buyer_id': holder.partner_id.id,
                'quantity': quantity,
                'price_per_unit': price,
                'state': 'done',
                'tx_hash': _fake_hash(rnd),
                'confirmed_on': fields.Datetime.now() - timedelta(
                    days=rnd.randint(0, 40), hours=rnd.randint(0, 23)),
            })


def _seed_owner(env, claims, rnd):
    """Дать владельцу стенда позиции и свой выпуск.

    Иначе он открывает биржу и видит рынок, на котором его самого нет:
    ни своих токенов, ни своих заявок, ни своих сделок — проверить
    сценарий «купил, держу, перепродаю» не на чем.
    """
    Holding = env['coop.token.holding'].sudo()
    Order = env['coop.token.order'].sudo()
    user = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    if not user:
        return
    me = user.partner_id
    if not me.coop_ton_address:
        me.write({
            'coop_ton_address': _fake_address(rnd),
            'coop_ton_network': 'testnet',
            'coop_ton_connected_on': fields.Datetime.now(),
        })
    pool = claims.filtered(
        lambda c: c.state == 'trading' and c.issuer_id != me)[:6]
    for claim in pool:
        if Holding.search_count([('claim_id', '=', claim.id),
                                 ('partner_id', '=', me.id)]):
            continue
        quantity = round(claim.quantity * rnd.uniform(0.05, 0.2), 1) or 1
        Holding.create({
            'claim_id': claim.id,
            'partner_id': me.id,
            'quantity': quantity,
            'acquired_on': fields.Datetime.now() - timedelta(days=rnd.randint(2, 60)),
        })
        # На часть купленного выставлена перепродажа: так на экране виден
        # и собственный след в стакане, помеченный «ваша».
        if rnd.random() < 0.5:
            Order.create({
                'claim_id': claim.id,
                'kind': 'secondary',
                'side': 'sell',
                'partner_id': me.id,
                'quantity': round(quantity * 0.6, 1) or quantity,
                'quantity_left': round(quantity * 0.6, 1) or quantity,
                'price_per_unit': round(claim.price_per_unit * rnd.uniform(1.05, 1.3), 4),
                'state': 'open',
                'import_key': 'tokens.order.owner#%s' % claim.id,
            })


def _spread_created(env, claims, rnd):
    """Развести даты размещения выпусков во времени.

    Демо создаётся за один прогон, и без этого все выпуски оказываются
    размещёнными сегодня: вкладка «Новые выпуски» показывает весь
    каталог, то есть не показывает ничего. Дата создания служебная и
    правится прямым запросом — обычной записью её не изменить.
    """
    for claim in claims:
        env.cr.execute(
            "UPDATE coop_token_claim SET create_date = now() - (%s || ' days')::interval "
            "WHERE id = %s", (rnd.randint(0, 120), claim.id))
    env.invalidate_all()


def _ensure_defaults(Claim, claims, today):
    """Хотя бы два сорванных выпуска на стенде.

    Жребием срыв выпадает не всегда — в первый прогон не выпал ни разу, и
    состояние, ради которого заведены и залог, и автовозврат, на экране
    было не увидеть. Проверять работу правила на данных, где оно ни разу
    не сработало, нельзя.
    """
    if Claim.search_count([('state', '=', 'defaulted')]) >= 2:
        return
    for claim in claims.filtered(lambda c: c.state == 'trading')[:2]:
        claim.write({
            'state': 'defaulted',
            'delivery_date': today - timedelta(days=12),
            'default_reason': 'Срок поставки прошёл, товар не передан',
        })


def _connect_wallets(Partner, partners, rnd):
    """Подключить участникам кошельки тестовой сети.

    Без кошелька участник не может ни выпустить, ни купить — а на пустой
    бирже проверить нечего. Адреса тестовые и сгенерированы: настоящий
    появится, когда участник подключит свой через TON Connect.
    """
    for partner in partners:
        if partner.coop_ton_address:
            continue
        partner.write({
            'coop_ton_address': _fake_address(rnd),
            'coop_ton_network': 'testnet',
            'coop_ton_connected_on': fields.Datetime.now(),
        })


def _make_orders_and_holdings(Order, Holding, claims, buyers, rnd, today):
    """Заявки и держатели.

    У торгующегося выпуска всегда есть первичная заявка поставщика — иначе
    купить у него нечего. Часть токенов уже куплена, и их держатели
    выставляют перепродажу: по её цене и видно, дорожает обещание или нет.
    """
    for claim in claims.filtered(lambda c: c.state in ('trading', 'delivering')):
        if claim.order_ids:
            continue
        sold = round(claim.quantity * rnd.uniform(0.15, 0.75), 1)
        Order.create({
            'claim_id': claim.id,
            'kind': 'primary',
            'side': 'sell',
            'partner_id': claim.issuer_id.id,
            'quantity': claim.quantity - sold,
            'quantity_left': claim.quantity - sold,
            'price_per_unit': claim.price_per_unit,
            'state': 'open',
            'import_key': 'tokens.order.primary#%s' % claim.id,
        })

        pool = [p for p in buyers if p != claim.issuer_id]
        holders = rnd.sample(pool, min(rnd.choice([1, 2, 3, 4]), len(pool)))
        left = sold
        for position, holder in enumerate(holders):
            share = round(left / (len(holders) - position), 1) if position < len(holders) - 1 else left
            if share <= 0:
                continue
            left -= share
            Holding.create({
                'claim_id': claim.id,
                'partner_id': holder.id,
                'quantity': share,
                'acquired_on': fields.Datetime.now() - timedelta(days=rnd.randint(1, 90)),
            })
            # Перепродажа: цена выше или ниже выпуска — рынок решает.
            if rnd.random() < 0.45:
                premium = rnd.uniform(-0.12, 0.35)
                Order.create({
                    'claim_id': claim.id,
                    'kind': 'secondary',
                    'side': 'sell',
                    'partner_id': holder.id,
                    'quantity': round(share * rnd.uniform(0.3, 1.0), 1) or share,
                    'quantity_left': round(share * rnd.uniform(0.3, 1.0), 1) or share,
                    'price_per_unit': round(claim.price_per_unit * (1 + premium), 4),
                    'state': 'open',
                    'import_key': 'tokens.order.sec#%s.%s' % (claim.id, holder.id),
                })
        # Заявки на покупку: «куплю по своей цене, если кто-то готов».
        if rnd.random() < 0.35:
            wanter = rnd.choice(pool)
            Order.create({
                'claim_id': claim.id,
                'kind': 'secondary',
                'side': 'buy',
                'partner_id': wanter.id,
                'quantity': round(claim.quantity * rnd.uniform(0.05, 0.25), 1) or 1,
                'quantity_left': round(claim.quantity * rnd.uniform(0.05, 0.25), 1) or 1,
                'price_per_unit': round(claim.price_per_unit * rnd.uniform(0.8, 1.05), 4),
                'state': 'open',
                'import_key': 'tokens.order.buy#%s' % claim.id,
            })


def _grant_project_shares(env):
    """Начислить доли по уже принятым вкладам.

    Вклады в проектах приняты давно, а механика долей появилась сейчас:
    начисляем задним числом по тем же правилам, что применились бы при
    принятии. Иначе раздел «Доли в проектах» пуст при восьмистах принятых
    вкладах, и понять, работает ли он, неоткуда.
    """
    Contribution = env['coop.project.contribution'].sudo()
    accepted = Contribution.search([
        ('state', '=', 'accepted'), ('share_tokens', '=', 0)])
    for project in accepted.mapped('project_id'):
        project.action_setup_share_rates()
    for contribution in accepted:
        contribution._grant_shares()
    _logger.info('Долей начислено по %s вкладам', len(accepted))


def _fake_address(rnd):
    """Тестовый адрес в формате, который разбирается библиотекой сети."""
    body = ''.join(rnd.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')
                   for _ in range(48))
    return '0:' + ''.join(rnd.choice('0123456789abcdef') for _ in range(64))


def _fake_hash(rnd):
    return ''.join(rnd.choice('0123456789abcdef') for _ in range(64))


def load_escrow(env, rnd=None):
    """Открыть эскроу по первичным сделкам.

    Раздел «Поставки» показывает, где лежат деньги покупателей. Пустым он
    выглядит так, будто механики нет вовсе, — а она и есть главное, что
    отличает обещание на товар от объявления.

    Состояния разложены по срокам: у будущих поставок деньги лежат, у
    прошедших либо расчёт завершён приёмкой, либо срок вышел и деньги
    вернулись. Спорные — отдельно: по ним видно, что платформа не решает
    за стороны, а ждёт, пока они разберутся.
    """
    import random as _random
    rnd = rnd or _random.Random(20260907)

    Escrow = env['coop.token.escrow'].sudo()
    Trade = env['coop.token.trade'].sudo()
    if Escrow.search_count([]) >= 40:
        _logger.info('Эскроу: уже наполнено, пропускаю')
        return

    today = fields.Date.context_today(Escrow)
    trades = Trade.search([('state', '=', 'done')])
    made = 0
    for trade in trades:
        if trade.order_id.kind != 'primary':
            continue
        if Escrow.search_count([('trade_id', '=', trade.id)]):
            continue
        due = trade.claim_id.delivery_date
        if not due:
            continue
        escrow = Escrow.create({
            'trade_id': trade.id,
            'buyer_id': trade.buyer_id.id,
            'seller_id': trade.seller_id.id,
            'amount': trade.total_price,
            'quantity': trade.quantity,
            'due_date': due,
        })
        if due < today:
            # Срок прошёл: чаще всего поставка состоялась, реже сорвалась,
            # изредка стороны спорят.
            outcome = rnd.choice(['released'] * 6 + ['refunded'] * 2 + ['dispute'])
            if outcome == 'released':
                escrow.write({
                    'state': 'released',
                    'delivered_on': fields.Datetime.now(),
                    'accepted_on': fields.Datetime.now(),
                    'settled_on': fields.Datetime.now(),
                })
            elif outcome == 'refunded':
                escrow.write({'state': 'refunded',
                              'settled_on': fields.Datetime.now()})
            else:
                escrow.write({
                    'disputed': True,
                    'dispute_note': rnd.choice([
                        'Привезли меньше заявленного объёма',
                        'Качество ниже указанного в выпуске',
                        'Поставка не в то место передачи',
                    ]),
                })
        elif rnd.random() < 0.25:
            # Часть поставщиков уже отметила отгрузку, покупатель ещё нет:
            # это самое частое промежуточное состояние.
            escrow.write({'delivered_on': fields.Datetime.now()})
        made += 1

    _logger.info('Эскроу: открыто %s записей', made)

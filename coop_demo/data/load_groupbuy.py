# -*- coding: utf-8 -*-
"""Совместные закупки: то, что кооперативы действительно берут вскладчину.

Товары взяты не с потолка: это позиции, ради которых складчина и
затевается — мешок дешевле фасовки, тонна дешевле мешка, а поодиночке
столько не нужно никому. Отсюда и объёмы: минимальный выкуп — это
реальная отгрузочная норма поставщика, а не круглое число.

Состояния разложены по срокам: часть закупок ещё собирает заказы, часть
уже раздана, а часть не состоялась — последнее важно показать. Складчина,
где всё всегда получается, вводит в заблуждение: не набрать объём —
обычный исход, и участник должен видеть его в каталоге.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Товар, единица, минимальный выкуп, цена при минимуме, шаги удешевления.
GOODS = [
    ('Комбикорм для КРС, мешки по 25 кг', 'мешок', 40, 1180,
     [(80, 1090), (150, 1010), (300, 940)]),
    ('Сахар-песок, мешки по 50 кг', 'мешок', 20, 3400,
     [(50, 3220), (100, 3080)]),
    ('Мука пшеничная в/с, мешки по 50 кг', 'мешок', 30, 1850,
     [(60, 1740), (120, 1650)]),
    ('Дизельное топливо, литры', 'л', 2000, 68,
     [(5000, 65), (10000, 62)]),
    ('Семена картофеля «Гала», элита', 'кг', 500, 92,
     [(1500, 84), (3000, 78)]),
    ('Плёнка для теплиц, рулоны 3×100 м', 'рулон', 15, 8600,
     [(30, 8100), (60, 7600)]),
    ('Сетка-рабица оцинкованная, рулоны', 'рулон', 25, 3150,
     [(50, 2950), (100, 2790)]),
    ('Доска обрезная сухая, кубометры', 'м³', 12, 18500,
     [(30, 17200), (60, 16400)]),
    ('Цемент М500, мешки по 50 кг', 'мешок', 60, 640,
     [(150, 590), (300, 545)]),
    ('Удобрение аммиачная селитра, тонны', 'т', 5, 27400,
     [(15, 25800), (30, 24500)]),
    ('Банки стеклянные 3 л, паллета', 'шт.', 300, 78,
     [(900, 71), (1800, 66)]),
    ('Утеплитель минеральный, упаковки', 'уп.', 40, 1420,
     [(100, 1330), (200, 1250)]),
    ('Ящики для овощей, полипропилен', 'шт.', 200, 165,
     [(600, 148), (1200, 136)]),
    ('Сахарная свёкла на семена, мешки', 'мешок', 25, 2900,
     [(60, 2740), (120, 2600)]),
    ('Бензин АИ-92, литры', 'л', 3000, 58,
     [(8000, 56), (15000, 54)]),
]

# Раздел по товару. Отдельной таблицей, а не седьмым полем в GOODS:
# список выше читается как прайс поставщика, и вклинивать в него
# служебный код значит испортить то, ради чего он такой.
CATEGORY = {
    'Комбикорм для КРС, мешки по 25 кг': 'feed',
    'Сахар-песок, мешки по 50 кг': 'grocery',
    'Мука пшеничная в/с, мешки по 50 кг': 'grocery',
    'Дизельное топливо, литры': 'fuel',
    'Семена картофеля «Гала», элита': 'seed',
    'Плёнка для теплиц, рулоны 3×100 м': 'build',
    'Сетка-рабица оцинкованная, рулоны': 'build',
    'Доска обрезная сухая, кубометры': 'build',
    'Цемент М500, мешки по 50 кг': 'build',
    'Удобрение аммиачная селитра, тонны': 'seed',
    'Банки стеклянные 3 л, паллета': 'pack',
    'Утеплитель минеральный, упаковки': 'build',
    'Ящики для овощей, полипропилен': 'pack',
    'Сахарная свёкла на семена, мешки': 'seed',
    'Бензин АИ-92, литры': 'fuel',
}

PICKUP = [
    'склад кооператива, ул. Заводская, 14',
    'площадка у элеватора',
    'гараж на Северной, заезд со двора',
    'ангар на выезде из города',
    'общий склад программы',
]

TARGET = 120


def _set_categories(Buy):
    """Раздел по названию товара. Название начинается с самого товара —
    город приписан после тире, — поэтому сверяем по началу строки."""
    for title, section in CATEGORY.items():
        Buy.search([('name', '=like', title + '%'),
                    ('category', 'in', (False, 'other'))]).write(
            {'category': section})


REJECTIONS = [
    'Поставщик не подтвердил объём — цена в карточке не обеспечена.',
    'Нет договора с поставщиком: на витрину такое не пускаем.',
    'Точка самовывоза не указана, забирать негде.',
    'Дубль уже идущей закупки того же товара в том же городе.',
]


def _set_roles(env):
    """Проставить роли на уже заведённых закупках.

    Роли появились позже самих закупок (решение 379 от 22 сентября), и у
    наполненной базы они пусты. Без этого прохода блок ролей на боевой
    показывал бы одного организатора — то есть ровно то, что решение и
    называло недоделкой.

    Разброс намеренный, а не для красоты. У части закупок поставщика на
    платформе нет вовсе — так и бывает: закупают у кого придётся, и
    требовать от каждого поставщика регистрации значило бы запретить
    половину закупок. У части нет отдельного оператора выдачи — выдаёт
    сам организатор. На витрине есть и отклонённые: раздел, где всё
    одобрено, не показывает, что модерация вообще работает.
    """
    Buy = env['coop.groupbuy'].sudo()
    Partner = env['res.partner'].sudo()
    buys = Buy.search([], order='id')
    if not buys:
        return

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not companies:
        return

    admin = env['res.users'].sudo().search(
        [('login', '=', 'dashkevich')], limit=1).partner_id

    rnd = random.Random(20260922)
    touched = 0
    for index, buy in enumerate(buys):
        values = {}

        if not buy.supplier_id and rnd.random() < 0.6:
            fit = companies.filtered(lambda c: c != buy.organizer_id)
            if fit:
                values['supplier_id'] = fit[index % len(fit)].id

        if not buy.pickup_operator_id and rnd.random() < 0.45:
            # Оператор — из своего города: за партией ездят, а не летают.
            near = (people.filtered(lambda p: p.city and p.city == buy.city)
                    or people)
            if near:
                values['pickup_operator_id'] = near[index % len(near)].id

        if admin and not buy.showcase_admin_id:
            values['showcase_admin_id'] = admin.id

        if buy.showcase_state == 'draft':
            chance = rnd.random()
            if chance < 0.8:
                values['showcase_state'] = 'published'
            elif chance < 0.88:
                values['showcase_state'] = 'rejected'
                values['showcase_note'] = REJECTIONS[index % len(REJECTIONS)]
            # Остальные так и остаются не выставленными — их ещё не
            # смотрели, и это тоже настоящее состояние.

        # Отметки участков — только там, где партия действительно ушла.
        if buy.state in ('delivering', 'handout', 'done') and not buy.shipped_on:
            values['shipped_on'] = buy.stop_date
        if buy.state in ('handout', 'done') and not buy.received_on:
            values['received_on'] = buy.delivery_date or buy.stop_date

        if values:
            buy.write(values)
            touched += 1

    _logger.info('Совместные закупки: роли проставлены у %s', touched)


def _set_pickup_codes(env):
    """Коды выдачи тем заказам, что были заведены до кодов."""
    Order = env['coop.groupbuy.order'].sudo()
    empty = Order.search(['|', ('pickup_code', '=', False),
                          ('pickup_code', '=', '')])
    for order in empty:
        order.pickup_code = Order._new_pickup_code()
    if empty:
        _logger.info('Совместные закупки: коды выдачи у %s заказов', len(empty))


def load_groupbuy(env, target=TARGET):
    Buy = env['coop.groupbuy'].sudo()
    Tier = env['coop.groupbuy.tier'].sudo()
    Order = env['coop.groupbuy.order'].sudo()
    Partner = env['res.partner'].sudo()

    if Buy.search_count([]) >= target // 2:
        _logger.info('Совместные закупки: уже наполнены, пропускаю')
        # Раздел появился позже самих закупок, и у наполненной базы он
        # пуст. Проставляем на уже заведённых — иначе полки каталога
        # увидит только тот, кто начал с чистой базы.
        _set_categories(Buy)
        _set_roles(env)
        _set_pickup_codes(env)
        return

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not companies or not people:
        _logger.warning('Нет участников — закупки не наполняю')
        return

    cities = sorted({p.city for p in companies if p.city}) or ['Москва']
    showcase = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    me = showcase.partner_id
    pool = [pid for pid in people.ids if pid != me.id]

    rnd = random.Random(20260907)
    today = fields.Date.context_today(Buy)
    created = 0

    for index in range(target):
        name, unit, min_volume, base, steps = GOODS[index % len(GOODS)]
        city = cities[index % len(cities)]
        organizer = companies[index % len(companies)]

        # Срок «стопа» задаёт состояние: будущие собирают, прошедшие уже
        # прошли свой путь. Так каталог сам собой выглядит живым, а не
        # набором записей в одном состоянии.
        offset = rnd.randint(-160, 25)
        stop_date = today + timedelta(days=offset)
        if offset > 0:
            state = 'collecting'
        else:
            state = rnd.choice(
                ['done'] * 5 + ['handout'] * 2 + ['delivering'] * 2
                + ['stopped'] + ['cancelled'] * 2)

        buy = Buy.create({
            'name': '%s — %s' % (name, city) if index >= len(GOODS) else name,
            'organizer_id': organizer.id,
            'supplier_name': rnd.choice([
                'ООО «Агроснаб»', 'Оптовая база №4', 'ТД «Зерновой»',
                'ИП Кузнецов', 'Комбинат «Северный»']),
            'city': city,
            'category': CATEGORY.get(name, 'other'),
            'pickup_point': rnd.choice(PICKUP),
            'unit_label': unit,
            'min_volume': min_volume,
            'base_price': base,
            'org_fee_percent': rnd.choice([5.0, 7.0, 8.0, 10.0]),
            'stop_date': stop_date,
            'delivery_date': stop_date + timedelta(days=rnd.randint(5, 20)),
            'description': '<p>Закупка партией у поставщика. Оргсбор включён '
                           'в цену, доплачивать при снижении уровня не '
                           'нужно.</p>',
            'state': state,
        })
        for from_qty, price in steps:
            Tier.create({'groupbuy_id': buy.id, 'from_quantity': from_qty,
                         'price': price})

        # Набранный объём: у несостоявшихся — заведомо меньше минимума,
        # у остальных — от минимума и выше. Иначе «не состоялась» стоит
        # рядом с полной полосой набора и выглядит ошибкой.
        if state == 'cancelled':
            share = rnd.uniform(0.2, 0.85)
        else:
            share = rnd.uniform(1.0, 2.6)
        wanted = min_volume * share

        buyers = rnd.sample(pool, rnd.randint(4, min(18, len(pool))))
        # Каждая шестая закупка — с участием того, под кем ведётся показ:
        # без своих заказов вкладка «мои закупки» пуста.
        if me and index % 6 == 0:
            buyers.append(me.id)
        left = wanted
        for position, partner_id in enumerate(buyers):
            last = position == len(buyers) - 1
            quantity = round(left if last else wanted / len(buyers)
                             * rnd.uniform(0.5, 1.6), 2)
            quantity = max(min(quantity, left), 0.01)
            left = round(left - quantity, 2)
            Order.create({
                'groupbuy_id': buy.id,
                'partner_id': partner_id,
                'quantity': quantity,
                'state': {
                    'collecting': 'draft', 'cancelled': 'cancelled',
                    'done': 'taken', 'handout': 'confirmed',
                }.get(state, 'confirmed'),
            })
            if left <= 0:
                break
        created += 1

    _spread_created(env, rnd)
    _set_roles(env)
    _set_pickup_codes(env)
    _logger.info('Совместные закупки: создано %s', created)


def _spread_created(env, rnd):
    """Развести даты создания — каталог сортируется по сроку, но лента по ним."""
    for record_id in env['coop.groupbuy'].sudo().search([]).ids:
        env.cr.execute(
            "UPDATE coop_groupbuy SET create_date = now() - (%s || ' days')::interval "
            "WHERE id = %s", (rnd.randint(0, 200), record_id))
    env.invalidate_all()

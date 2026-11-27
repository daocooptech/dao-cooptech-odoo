# -*- coding: utf-8 -*-
"""Склад витрины dashkevich — для штатного дашборда «Показатели склада»
(решение 707, задача 494).

У «Вектор Инжиниринг» товары из объявлений — расходные, остатков нет, и
дашборд склада пуст. Здесь у витрины заводятся складские позиции
инженерной компании, остатки по трём местам хранения (проводкой
инвентаризации — с движениями и стоимостью), 50 заказов продаж по ним;
отгрузки по подтверждённым заказам проводятся.

Повторяемо: позиции — по имени в компании, места — по имени, заказы — по
ключу `coop_demo.sos_<орг>_<n>`.
"""
import logging
import random
from datetime import datetime, timedelta

from . import load_sales as ls

_logger = logging.getLogger(__name__)

# Название, категория, цена продажи, закупки (₽)
GOODS = [
    ('Кабель ВВГнг-LS 3×2,5, м', 'Кабель и провод', 112, 78),
    ('Кабель ВВГнг-LS 5×4, м', 'Кабель и провод', 298, 214),
    ('Кабель КГтп 4×6, м', 'Кабель и провод', 356, 251),
    ('Провод ПуГВ 1×6, м', 'Кабель и провод', 64, 43),
    ('Кабель витая пара U/UTP cat.5e, м', 'Кабель и провод', 29, 18),
    ('Автоматический выключатель 1P C16', 'Электрощитовое', 540, 362),
    ('Автоматический выключатель 3P C32', 'Электрощитовое', 1980, 1390),
    ('УЗО 2P 40 А 30 мА', 'Электрощитовое', 2650, 1840),
    ('Дифавтомат 1P+N C20 30 мА', 'Электрощитовое', 2240, 1560),
    ('Щит распределительный ЩРН-24', 'Электрощитовое', 4300, 2950),
    ('Контактор КМИ 25 А 230 В', 'Электрощитовое', 1750, 1180),
    ('Счётчик электроэнергии трёхфазный', 'Электрощитовое', 6900, 4850),
    ('Светильник светодиодный 36 Вт IP65', 'Освещение', 1890, 1240),
    ('Прожектор светодиодный 100 Вт', 'Освещение', 3200, 2150),
    ('Светильник аварийный «Выход»', 'Освещение', 1450, 960),
    ('Труба гофрированная ПВХ 20 мм, м', 'Монтажные изделия', 21, 12),
    ('Лоток кабельный перфорированный 100×50, 3 м', 'Монтажные изделия', 890, 610),
    ('Короб кабельный 40×25, 2 м', 'Монтажные изделия', 148, 96),
    ('Анкер клиновой 10×100, упак. 50 шт.', 'Монтажные изделия', 1280, 840),
    ('Хомут нейлоновый 300 мм, упак. 100 шт.', 'Монтажные изделия', 390, 240),
    ('Труба полипропиленовая PN20 25 мм, 4 м', 'Сантехника и отопление', 410, 270),
    ('Радиатор биметаллический 10 секций', 'Сантехника и отопление', 9800, 7100),
    ('Кран шаровой латунный 1"', 'Сантехника и отопление', 1150, 760),
    ('Насос циркуляционный 25-60', 'Сантехника и отопление', 8700, 6200),
    ('Счётчик воды 15 мм', 'Сантехника и отопление', 1290, 850),
    ('Воздуховод оцинкованный 160 мм, 1 м', 'Вентиляция', 640, 430),
    ('Вентилятор канальный 160 мм', 'Вентиляция', 5400, 3800),
    ('Решётка вентиляционная 200×200', 'Вентиляция', 520, 330),
    ('Клапан обратный 160 мм', 'Вентиляция', 980, 650),
    ('Датчик температуры с выносным зондом', 'Автоматика', 2350, 1610),
    ('Реле времени модульное', 'Автоматика', 2900, 1980),
    ('Преобразователь частоты 2,2 кВт', 'Автоматика', 21400, 15800),
    ('Блок питания 24 В 5 А на DIN-рейку', 'Автоматика', 3100, 2120),
    ('Перфоратор SDS-plus 800 Вт', 'Инструмент', 11900, 8600),
    ('Шуруповёрт аккумуляторный 18 В', 'Инструмент', 8900, 6300),
    ('Мультиметр цифровой', 'Инструмент', 2700, 1790),
    ('Набор отвёрток диэлектрических', 'Инструмент', 2150, 1420),
    ('Каска защитная', 'Средства защиты', 690, 420),
    ('Перчатки диэлектрические', 'Средства защиты', 980, 640),
    ('Очки защитные открытые', 'Средства защиты', 310, 190),
]
PLACES = ['Стеллаж А', 'Стеллаж Б', 'Площадка под навесом']
ORDERS = 50


def _category(env, name):
    Cat = env['product.category'].sudo()
    return Cat.search([('name', '=', name)], limit=1) or Cat.create({'name': name})


def load_showcase_stock(env, login='dashkevich'):
    if 'stock.quant' not in env or 'sale.order' not in env:
        return 0
    showcase = ls._showcase(env, login).filtered(lambda o: o in ls._orgs(env))
    clients = env['res.partner'].sudo().search([('coop_is_participant', '=', True)], order='id')
    today = datetime.now().replace(second=0, microsecond=0)
    made = 0
    for org in showcase:
        company = org.coop_company_id
        holders = ls._holders(env, org, 'sales_team.group_sale_salesman')
        warehouse = env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        if not holders or not warehouse:
            continue
        rnd = random.Random(20261128 + org.id)
        Loc = env['stock.location'].sudo()
        places = Loc.browse()
        for name in PLACES:
            places |= Loc.search([('name', '=', name), ('location_id', '=', warehouse.lot_stock_id.id)], limit=1) \
                or Loc.create({'name': name, 'location_id': warehouse.lot_stock_id.id,
                               'usage': 'internal', 'company_id': company.id})
        Product = env['product.product'].sudo().with_company(company)
        products = Product.browse()
        for name, categ, price, cost in GOODS:
            product = Product.search([('name', '=', name), ('company_id', '=', company.id)], limit=1)
            if not product:
                product = Product.create({
                    'name': name, 'company_id': company.id, 'type': 'consu',
                    'is_storable': True, 'categ_id': _category(env, categ).id,
                    'list_price': price, 'standard_price': cost,
                    'sale_ok': True, 'purchase_ok': True,
                })
                Quant = env['stock.quant'].sudo().with_company(company).with_context(inventory_mode=True)
                for place in rnd.sample(list(places), k=rnd.randint(1, 3)):
                    qty = rnd.choice((5, 10, 20, 40, 60, 100, 150, 300, 500)) if price < 3000 \
                        else rnd.randint(3, 40)
                    Quant.create({'product_id': product.id, 'location_id': place.id,
                                  'inventory_quantity': qty}).action_apply_inventory()
            products |= product
        for number in range(ORDERS):
            xmlid = ls._key(env, 'sos', org, number)
            if ls._have(env, xmlid):
                continue
            client = clients[rnd.randrange(len(clients))]
            if client == org or client.user_ids & holders:
                continue
            state = ls._sale_state(rnd)
            moment = ls._when(rnd, today, state)
            lines = [(0, 0, {'product_id': p.id,
                             'product_uom_qty': rnd.choice((1, 2, 3, 5, 10)),
                             'price_unit': p.list_price})
                     for p in rnd.sample(list(products), k=rnd.randint(1, 4))]
            try:
                with env.cr.savepoint():
                    order = env['sale.order'].sudo().with_company(company).create({
                        'partner_id': client.id, 'company_id': company.id,
                        'user_id': holders[rnd.randrange(len(holders))].id,
                        'team_id': ls._team(env, company).id, 'order_line': lines,
                        'note': rnd.choice(ls.SO_NOTES) or False,
                    })
                    ls._no_vat(org, order, moment)
                    if state == 'sent':
                        order.write({'state': 'sent'})
                    elif state in ('sale', 'invoiced'):
                        order.with_context(mail_notrack=True).action_confirm()
                        # Отгружено — большинство подтверждённых, свежие ещё ждут.
                        if rnd.random() < 0.75:
                            for picking in order.picking_ids:
                                # Резерв — со стеллажей, иначе списание идёт с корня склада в минус.
                                picking.action_assign()
                                for move in picking.move_ids:
                                    move.quantity = move.product_uom_qty
                                    move.picked = True
                                picking.with_context(skip_backorder=True, skip_sms=True)._action_done()
                        if state == 'invoiced':
                            invoice = order._create_invoices()
                            if rnd.random() < 0.8:
                                invoice.action_post()
                    elif state == 'cancel':
                        order.with_context(disable_cancel_warning=True).action_cancel()
                    ls._mark(env, xmlid, order)
                    ls._date_sale(env, order, moment)
                    env.cr.execute(
                        "UPDATE stock_picking SET date_done = %s WHERE sale_id = %s AND state = 'done'",
                        (moment + timedelta(days=2), order.id))
                    made += 1
            except Exception as exc:  # noqa: BLE001 — одна неудача не роняет загрузку
                _logger.warning('Склад витрины: заказ %s не заведён: %s', xmlid, ls._flat(exc))
    _logger.info('Склад витрины: заказов заведено %s', made)
    return made

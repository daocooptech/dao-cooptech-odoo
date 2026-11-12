# -*- coding: utf-8 -*-
"""Заказы продаж и закупок организаций — наше демо вместо образца Odoo
(решение 655, п. 1; задача 431).

Пустые «Продажи» и «Закупки» Odoo заполняет образцом с латинскими
именами (John Miller, «Viverra nam»). Записей за ним нет. Образец
пропадает, когда у раздела появляются свои записи, поэтому здесь заводятся
настоящие заказы от имени организаций площадки.

- Продажи: продаёт организация со своей компанией учёта, складом и
  держателем полномочия «Сделки». Строки заказа — её объявления о ресурсах
  (цена из объявления). Покупатель — другая организация или человек.
  Состояния: черновик, отправлено, подтверждено, подтверждено со счётом,
  отменено.
- Закупки: закупает организация с включённым приложением «Закупки» и
  складом, поставщик — другая организация, строки — объявления
  поставщика. Состояния: запрос цены, отправлен, на согласовании,
  подтверждено, подтверждено со счётом поставщика, отменено.
- Даты разнесены по году, черновики — свежие.

Витрина под `dashkevich` — «Вектор Инжиниринг»: у неё продаж и закупок
больше, чем у остальных.

Повторяемо: заказ помечен внешним ключом `coop_demo.so_<орг>_<n>` /
`coop_demo.po_<орг>_<n>`, уже заведённое пропускается. Жребий — от номера
организации.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

try:
    from odoo.addons.coop_invoicing.models.coop_vat_regime import NO_VAT_REGIMES
except ImportError:  # coop_invoicing не установлен — налоги не трогаем
    NO_VAT_REGIMES = ()

SO_TARGET = 160
PO_TARGET = 130

SO_NOTES = [
    'Отгрузка со склада продавца, самовывоз.',
    'Доставка транспортной компанией за счёт покупателя.',
    'Предоплата 30 %, остальное — после приёмки.',
    'Оплата по факту поставки в течение 10 рабочих дней.',
    'Партия по рамочному договору, цена зафиксирована на квартал.',
    '',
]
PO_NOTES = [
    'Сертификаты и декларации — вместе с партией.',
    'Поставка на склад покупателя, разгрузка силами поставщика.',
    'Цена согласована по итогам запроса трём поставщикам.',
    'Сезонная закупка, срок поставки критичен.',
    '',
]


def _flat(exc):
    return ' '.join(str(exc).split())[:700]


def _no_vat(org, order, moment):
    """Организация без режима НДС налог в строки не ставит: проверка
    coop_tax иначе отказывает счёту («выставленный НДС пришлось бы
    уплатить»)."""
    regime_at = getattr(org, '_coop_vat_regime_at', None)
    if not regime_at:
        return
    # Счёт проверяется по дате проводки — сегодня; заказ датирован прошлым.
    if not {regime_at(moment.date()), regime_at(datetime.now().date())} & set(NO_VAT_REGIMES):
        return
    lines = order.order_line
    for name in ('tax_ids', 'tax_id', 'taxes_id'):
        if name in lines._fields:
            lines.write({name: [(5,)]})
            return


def _team(env, company):
    Team = env['crm.team'].sudo()
    team = Team.search([('company_id', '=', company.id)], limit=1)
    if not team:
        team = Team.search([('company_id', '=', False)], limit=1)
    return team


def _key(env, prefix, org, number):
    return 'coop_demo.%s_%s_%s' % (prefix, org.id, number)


def _have(env, xmlid):
    return bool(env.ref(xmlid, raise_if_not_found=False))


def _mark(env, xmlid, record):
    module, name = xmlid.split('.')
    env['ir.model.data'].sudo().create({
        'module': module, 'name': name, 'model': record._name,
        'res_id': record.id, 'noupdate': True,
    })


def _count(env, model, prefix):
    return env['ir.model.data'].sudo().search_count([
        ('module', '=', 'coop_demo'), ('model', '=', model),
        ('name', '=like', prefix + '\\_%')])


def _product(env, company, resource, rnd):
    Product = env['product.product'].sudo().with_company(company)
    name = resource.name[:120]
    product = Product.search([('name', '=', name), ('company_id', '=', company.id)], limit=1)
    if not product:
        price = resource.price or rnd.randrange(300, 90000, 10)
        product = Product.create({
            'name': name, 'company_id': company.id, 'type': 'consu',
            'list_price': price, 'standard_price': round(price * 0.7, 2),
            'sale_ok': True, 'purchase_ok': True,
        })
    return product


def _offers(env, org):
    return env['coop.resource'].sudo().with_context(active_test=False).search([
        ('owner_id', '=', org.id), ('listing_type', '=', 'offer')], order='id', limit=12)


def _holders(env, org, group):
    return env['coop.membership'].sudo().search([
        ('organization_id', '=', org.id), ('state', '=', 'active'),
        ('power_ids.code', '=', 'deal')]).partner_id.user_ids.filtered(
        lambda u: not u.share and org.coop_company_id in u.company_ids
        and u.has_group(group))


def _when(rnd, today, state):
    # Черновики и отправленные — последние два месяца, остальное — год.
    days = rnd.randint(0, 60) if state in ('draft', 'sent', 'to approve') else rnd.randint(5, 360)
    return today - timedelta(days=days, hours=rnd.randint(0, 9), minutes=rnd.randint(0, 59))


def _showcase(env, login):
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user:
        return env['res.partner']
    return env['coop.membership'].sudo().search([
        ('partner_id', '=', user.partner_id.id), ('state', '=', 'active'),
        ('power_ids.code', '=', 'deal')]).organization_id.filtered('coop_company_id')


def _orgs(env, extra_domain=()):
    with_wh = env['stock.warehouse'].sudo().search([]).company_id
    orgs = env['res.partner'].sudo().search([
        ('is_company', '=', True), ('coop_is_participant', '=', True),
        ('coop_company_id', '!=', False)] + list(extra_domain), order='id')
    return orgs.filtered(lambda o: o.coop_company_id in with_wh)


def _sale_state(rnd):
    roll = rnd.random()
    if roll < 0.18:
        return 'draft'
    if roll < 0.32:
        return 'sent'
    if roll < 0.58:
        return 'sale'
    if roll < 0.85:
        return 'invoiced'
    return 'cancel'


def _purchase_state(rnd):
    roll = rnd.random()
    if roll < 0.18:
        return 'draft'
    if roll < 0.28:
        return 'sent'
    if roll < 0.34:
        return 'to approve'
    if roll < 0.62:
        return 'purchase'
    if roll < 0.86:
        return 'billed'
    return 'cancel'


def load_sales(env, login='dashkevich', target=SO_TARGET):
    if 'sale.order' not in env:
        return 0
    have = _count(env, 'sale.order', 'so')
    if have >= target:
        _logger.info('Продажи: заказов уже %s, пропускаю', have)
        return 0
    showcase = _showcase(env, login)
    sellers = _orgs(env)
    clients = env['res.partner'].sudo().search([('coop_is_participant', '=', True)], order='id')
    today = datetime.now().replace(second=0, microsecond=0)
    made = 0
    # Витрина — первой, чтобы её заказы появились и при малом остатке.
    ordered = showcase.filtered(lambda o: o in sellers) + (sellers - showcase)
    for org in ordered:
        if have + made >= target:
            break
        rnd = random.Random(20261113 + org.id)
        offers = _offers(env, org)
        holders = _holders(env, org, 'sales_team.group_sale_salesman')
        if not offers or not holders:
            continue
        company = org.coop_company_id
        count = rnd.randint(8, 14) if org in showcase else rnd.choice((0, 1, 1, 2, 2, 3))
        for number in range(count):
            xmlid = _key(env, 'so', org, number)
            if _have(env, xmlid):
                continue
            client = clients[rnd.randrange(len(clients))]
            if client == org or client.user_ids & holders:
                continue
            state = _sale_state(rnd)
            moment = _when(rnd, today, state)
            seller = holders[rnd.randrange(len(holders))]
            lines = []
            for resource in rnd.sample(list(offers), k=min(len(offers), rnd.randint(1, 3))):
                product = _product(env, company, resource, rnd)
                lines.append((0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': rnd.choice((1, 2, 3, 5, 10, 12, 20, 50)),
                    'price_unit': product.list_price,
                }))
            try:
                with env.cr.savepoint():
                    order = env['sale.order'].sudo().with_company(company).create({
                        'partner_id': client.id,
                        'company_id': company.id,
                        'user_id': seller.id,
                        'team_id': _team(env, company).id,
                        'order_line': lines,
                        'note': rnd.choice(SO_NOTES) or False,
                        'client_order_ref': rnd.random() < 0.4 and 'Заявка № %s' % rnd.randint(100, 9999) or False,
                    })
                    _no_vat(org, order, moment)
                    if state == 'sent':
                        order.write({'state': 'sent'})
                    elif state in ('sale', 'invoiced'):
                        order.with_context(mail_notrack=True).action_confirm()
                        if state == 'invoiced':
                            invoice = order._create_invoices()
                            if rnd.random() < 0.8:
                                invoice.action_post()
                        if rnd.random() < 0.3:
                            order.action_lock()
                    elif state == 'cancel':
                        order.with_context(disable_cancel_warning=True).action_cancel()
                    _mark(env, xmlid, order)
                    _date_sale(env, order, moment)
                    made += 1
            except Exception as exc:  # noqa: BLE001 — одна неудача не роняет загрузку
                _logger.warning('Продажи: заказ %s не заведён: %s', xmlid, _flat(exc))
    _logger.info('Продажи: заказов заведено %s', made)
    return made


def _date_sale(env, order, moment):
    env.flush_all()
    cr = env.cr
    cr.execute('UPDATE sale_order SET date_order = %s, create_date = %s WHERE id = %s',
               (moment, moment, order.id))
    if order.state == 'sale':
        cr.execute('UPDATE stock_picking SET scheduled_date = %s, create_date = %s '
                   'WHERE sale_id = %s', (moment + timedelta(days=3), moment, order.id))
    for move in order.invoice_ids:
        day = (moment + timedelta(days=2)).date()
        cr.execute('UPDATE account_move SET invoice_date = %s, date = %s, '
                   'invoice_date_due = %s WHERE id = %s',
                   (day, day, day + timedelta(days=10), move.id))
        cr.execute('UPDATE account_move_line SET date = %s WHERE move_id = %s', (day, move.id))
    order.invalidate_recordset()


def load_purchases(env, login='dashkevich', target=PO_TARGET):
    if 'purchase.order' not in env:
        return 0
    have = _count(env, 'purchase.order', 'po')
    if have >= target:
        _logger.info('Закупки: заказов уже %s, пропускаю', have)
        return 0
    showcase = _showcase(env, login)
    domain = [('coop_app_purchase', '=', True)] if 'coop_app_purchase' in env['res.partner']._fields else []
    buyers = _orgs(env, domain)
    vendors = env['res.partner'].sudo().search([
        ('is_company', '=', True), ('coop_is_participant', '=', True)], order='id')
    vendors = vendors.filtered(lambda v: _offers(env, v))
    today = datetime.now().replace(second=0, microsecond=0)
    made = 0
    ordered = (showcase & buyers) + (buyers - showcase)
    for org in ordered:
        if have + made >= target:
            break
        rnd = random.Random(20261114 + org.id)
        holders = _holders(env, org, 'purchase.group_purchase_user')
        if not holders or not vendors:
            continue
        company = org.coop_company_id
        count = rnd.randint(6, 10) if org in showcase else rnd.choice((0, 1, 1, 2, 2))
        for number in range(count):
            xmlid = _key(env, 'po', org, number)
            if _have(env, xmlid):
                continue
            vendor = vendors[rnd.randrange(len(vendors))]
            if vendor == org:
                continue
            state = _purchase_state(rnd)
            buyer = holders[rnd.randrange(len(holders))]
            offers = _offers(env, vendor)
            moment = _when(rnd, today, state)
            lines = []
            for resource in rnd.sample(list(offers), k=min(len(offers), rnd.randint(1, 3))):
                product = _product(env, company, resource, rnd)
                lines.append((0, 0, {
                    'product_id': product.id,
                    'product_qty': rnd.choice((1, 2, 5, 10, 20, 40, 100)),
                    'price_unit': round(product.list_price * rnd.uniform(0.85, 1.0), 2),
                    'date_planned': moment + timedelta(days=rnd.randint(3, 30)),
                }))
            try:
                with env.cr.savepoint():
                    order = env['purchase.order'].sudo().with_company(company).create({
                        'partner_id': vendor.id,
                        'company_id': company.id,
                        'user_id': buyer.id,
                        'order_line': lines,
                        'note': rnd.choice(PO_NOTES) or False,
                        'partner_ref': rnd.random() < 0.5 and 'КП-%s' % rnd.randint(10, 999) or False,
                    })
                    _no_vat(org, order, moment)
                    if state == 'sent':
                        order.write({'state': 'sent'})
                    elif state == 'to approve':
                        order.write({'state': 'to approve'})
                    elif state in ('purchase', 'billed'):
                        order.button_confirm()
                        if state == 'billed':
                            order.action_create_invoice()
                            bill = order.invoice_ids[:1]
                            if bill:
                                bill.invoice_date = moment.date()
                                if rnd.random() < 0.75:
                                    bill.action_post()
                    elif state == 'cancel':
                        order.button_cancel()
                    _mark(env, xmlid, order)
                    _date_purchase(env, order, moment)
                    made += 1
            except Exception as exc:  # noqa: BLE001
                _logger.warning('Закупки: заказ %s не заведён: %s', xmlid, _flat(exc))
    _logger.info('Закупки: заказов заведено %s', made)
    return made


def _date_purchase(env, order, moment):
    env.flush_all()
    cr = env.cr
    cr.execute('UPDATE purchase_order SET date_order = %s, create_date = %s, '
               'date_approve = CASE WHEN state = \'purchase\' THEN %s ELSE NULL END '
               'WHERE id = %s', (moment, moment, moment + timedelta(hours=5), order.id))
    for move in order.invoice_ids:
        day = (moment + timedelta(days=4)).date()
        cr.execute('UPDATE account_move SET invoice_date = %s, date = %s, '
                   'invoice_date_due = %s WHERE id = %s',
                   (day, day, day + timedelta(days=14), move.id))
        cr.execute('UPDATE account_move_line SET date = %s WHERE move_id = %s', (day, move.id))
    order.invalidate_recordset()

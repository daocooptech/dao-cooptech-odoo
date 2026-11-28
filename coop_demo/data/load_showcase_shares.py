# -*- coding: utf-8 -*-
"""Пайщики витрины dashkevich — для дашборда «Аналитика → Пайщики»
(задача 494, кусок 5; владелец 28.11.2026: «dashkevich в правление»).

Раздел видят правление, ревизия и администратор; правлению — счета своего
кооператива. dashkevich — пайщик СПК «Степь», но не в правлении, и без
режима администратора раздела у него не было. Здесь: он — член правления
«Степи», а у «Степи» — 150 пайщиков (было 19) с историей паёв: вступительный
и паевой взносы, дополнительные взносы, начисления по итогам года,
выплаты, выходы с возвратом пая и заявления на рассмотрении.
Повторяемо: членство — одно на человека и кооператив, движения заводятся
только на новых счетах.
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

COOP = 'СПК «Степь»'
MEMBERS = 150


def _move(Move, account, when, kind, name, basis, amount, state='confirmed'):
    Move.create({'account_id': account.id, 'date': when, 'name': name, 'kind': kind,
                 'basis': basis, 'amount': amount, 'state': state})


def load_showcase_shares(env, login='dashkevich'):
    if 'coop.share.account' not in env:
        return 0
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    coop = env['res.partner'].sudo().search(
        [('name', '=', COOP), ('is_company', '=', True)], limit=1)
    if not user or not coop:
        return 0
    Membership = env['coop.membership'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    mine = Membership.search([('partner_id', '=', user.partner_id.id),
                              ('organization_id', '=', coop.id)], limit=1)
    if mine and mine.role != 'board':
        mine.role = 'board'
    board = env.ref('coop_base.group_coop_board', raise_if_not_found=False)
    if board:
        # Своя группа, а не выданная переключателем администратора: тот
        # при выключении снимает всё, что добавил сам (`coop_admin`).
        vals = {'group_ids': [(4, board.id)]}
        if 'coop_admin_added_group_ids' in user._fields:
            vals['coop_admin_added_group_ids'] = [(3, board.id)]
        user.sudo().write(vals)

    have = Membership.search([('organization_id', '=', coop.id)])
    members = set(have.partner_id.ids)
    people = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('id', 'not in', list(members)), ('name', 'not ilike', 'Проба')], order='id')
    rnd = random.Random(20261128 + coop.id)
    today = date.today()
    Wallet = env['coop.wallet'].sudo()
    Move = env['coop.share.move'].sudo().with_context(tracking_disable=True)
    made = 0
    for person in people:
        if len(members) >= MEMBERS:
            break
        joined = today - timedelta(days=rnd.randint(20, 1400))
        roll = rnd.random()
        state = 'ended' if roll < 0.06 else 'leaving' if roll < 0.14 else (
            'applied' if roll < 0.18 else 'active')
        try:
            with env.cr.savepoint():
                Membership.create({
                    'partner_id': person.id, 'organization_id': coop.id,
                    'role': 'member', 'state': state, 'joined_on': joined,
                    'admission_basis': 'Протокол общего собрания пайщиков № %d от %s'
                    % (rnd.randint(2, 40), joined.strftime('%d.%m.%Y')),
                })
                wallet = Wallet.wallet_for(person)
                account = wallet.share_account_ids.filtered(
                    lambda a: a.cooperative_id == coop)
                if not account or account.move_ids:
                    members.add(person.id)
                    continue
                if state == 'applied':
                    _move(Move, account, joined, 'entry', 'Вступительный взнос',
                          'Заявление о приёме', 2000, 'requested')
                    members.add(person.id)
                    made += 1
                    continue
                _move(Move, account, joined, 'entry', 'Вступительный взнос',
                      'Протокол общего собрания о приёме', rnd.choice((1000, 2000, 3000)))
                _move(Move, account, joined, 'share', 'Обязательный паевой взнос',
                      'Протокол общего собрания о приёме', 50000)
                if rnd.random() < 0.35:
                    _move(Move, account, joined + timedelta(days=rnd.randint(30, 300)),
                          'extra', 'Дополнительный паевой взнос', 'Заявление пайщика',
                          rnd.randrange(10000, 200000, 5000))
                year = joined.year
                while year < today.year:
                    year += 1
                    _move(Move, account, date(year, 4, rnd.randint(1, 28)), 'accrual',
                          'Начисление по итогам %s года' % (year - 1),
                          'Протокол годового общего собрания',
                          rnd.randrange(1500, 18000, 100))
                if rnd.random() < 0.12:
                    _move(Move, account, today - timedelta(days=rnd.randint(1, 200)),
                          'payout', 'Выплата начисленного на руки', 'Заявление пайщика',
                          -rnd.randrange(1000, 8000, 100))
                if rnd.random() < 0.05:
                    _move(Move, account, today - timedelta(days=rnd.randint(1, 20)),
                          'payout', 'Заявление на выплату', 'Заявление пайщика',
                          -rnd.randrange(2000, 9000, 100), 'requested')
                if state == 'ended':
                    account.invalidate_recordset()
                    _move(Move, account, today - timedelta(days=rnd.randint(10, 200)),
                          'return', 'Возврат пая при выходе', 'Протокол общего собрания',
                          -account.balance)
                members.add(person.id)
                made += 1
        except Exception as exc:  # noqa: BLE001 — один отказ не роняет загрузку
            _logger.warning('Пайщики витрины: %s — %s', person.display_name, exc)
    _logger.info('Пайщики витрины: новых пайщиков «%s» %s, всего %s', COOP, made,
                 len(members))
    return made

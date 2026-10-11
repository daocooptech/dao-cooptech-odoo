# -*- coding: utf-8 -*-
"""Состояния демо-данных: задачи проектов, бартер, биржа токенов, DEX.

Замечание владельца 11.10.2026: наполнение однобокое. В задачах проектов
70% «Готово»; на бирже токенов 1202 заявки из 1220 «в стакане», нет ни
снятых, ни исполненных; в DEX 662 из 726 объявлений активны, ни одного
«частично»; в сделках токенов нет «в сети» и «не прошла»; в бартере нет
черновиков.

Проход не добавляет записей, а доводит состояния до того, что бывает на
действующей площадке, и достраивает связанное: исполненной заявке нужна
сделка, частично исполненной — остаток. Решение, какую запись менять,
принимается по хэшу её номера: повторный прогон тех же записей не
трогает, а новые не пропускает.
"""
import hashlib
import logging
import random
from datetime import datetime, timedelta

from . import load_project_tasks

_logger = logging.getLogger(__name__)

# Как идут задачи в проектах, пока проект не завершён: доля закрытых
# задач, которую оставляем «Готово», и куда уходит остальное
# (идея / в работе / на проверке).
TASK_KEEP_DONE = {
    'preparation': (0.15, (0.70, 0.25, 0.05)),
    'supply': (0.30, (0.35, 0.50, 0.15)),
    'work': (0.38, (0.15, 0.55, 0.30)),
    'acceptance': (0.65, (0.00, 0.20, 0.80)),
}


def _bucket(model, rec_id, salt=''):
    """Число 0..1, стабильное для записи: от него зависит, менять ли её."""
    digest = hashlib.md5(('%s:%s:%s' % (model, rec_id, salt)).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _pick(bucket, steps):
    """steps — [(верхняя граница, значение)...] по возрастанию."""
    for edge, value in steps:
        if bucket < edge:
            return value
    return None


def load_market_mix(env):
    done = {
        'tasks': _mix_tasks(env),
        'token_orders': _mix_token_orders(env),
        'token_trades': _mix_token_trades(env),
        'crypto_offers': _mix_crypto_offers(env),
        'crypto_trades': _mix_crypto_trades(env),
        'barter_offers': _mix_barter_offers(env),
    }
    _logger.info('Состояния демо-данных доведены: %s', done)
    return done


# ── Задачи проектов ────────────────────────────────────────────────────
def _mix_tasks(env):
    if 'project.task' not in env:
        return 0
    Task = env['project.task'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    stages = load_project_tasks._ensure_stages(
        env['project.task.type'].sudo(), env['project.project'].sudo())
    changed = 0
    for key, (keep, spread) in TASK_KEEP_DONE.items():
        stage = env.ref('coop_projects.project_stage_%s' % key,
                        raise_if_not_found=False)
        if not stage:
            continue
        tops = Task.search([
            ('project_id.stage_id', '=', stage.id),
            ('parent_id', '=', False), ('state', '=', '1_done')])
        for task in tops:
            if _bucket('task', task.id) < keep:
                continue
            _reopen(Task, task, spread, stages)
            changed += 1
            # Подзадачи открытой задачи закрыты не все.
            for sub in task.child_ids.filtered(lambda t: t.state == '1_done'):
                if _bucket('subtask', sub.id) < 0.35:
                    continue
                _reopen(Task, sub, spread, stages)
                changed += 1
    return changed


def _reopen(Task, task, spread, stages):
    pick = _bucket('where', task.id)
    first, second, _third = spread
    if pick < first:
        stage = stages['idea']
    elif pick < first + second:
        stage = stages['doing']
    else:
        stage = stages['review']
    waiting = _bucket('wait', task.id) < 0.15
    task.write({
        'stage_id': stage,
        'state': '04_waiting_normal' if waiting and stage == stages['idea']
        else '01_in_progress',
        'date_end': False,
    })


# ── Биржа токенов ──────────────────────────────────────────────────────
def _traders(env):
    return env['res.partner'].sudo().search(
        [('coop_ton_address', '!=', False)], limit=400)


def _fake_hash(rnd):
    return ''.join(rnd.choice('0123456789abcdef') for _ in range(64))


def _mix_token_orders(env):
    if 'coop.token.order' not in env:
        return 0
    Order = env['coop.token.order'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    Trade = env['coop.token.trade'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    traders = _traders(env)
    if len(traders) < 5:
        return 0
    rnd = random.Random(20261011)
    now = datetime.now().replace(microsecond=0)
    changed = 0
    for order in Order.search([('state', '=', 'open')], order='id'):
        verdict = _pick(_bucket('order', order.id), [
            (0.04, 'draft'), (0.16, 'cancelled'),
            (0.24, 'partial'), (0.34, 'done')])
        if not verdict:
            continue
        if verdict in ('draft', 'cancelled'):
            order.write({'state': verdict})
            changed += 1
            continue
        others = traders.filtered(lambda p: p != order.partner_id)
        if not others:
            continue
        other = rnd.choice(others)
        filled = order.quantity if verdict == 'done' else round(
            order.quantity * rnd.uniform(0.15, 0.7), 3) or order.quantity
        seller, buyer = ((order.claim_id.issuer_id or order.partner_id, other)
                         if order.kind == 'primary' else
                         (order.partner_id, other) if order.side == 'sell'
                         else (other, order.partner_id))
        Trade.create({
            'order_id': order.id,
            'claim_id': order.claim_id.id,
            'seller_id': seller.id,
            'buyer_id': buyer.id,
            'quantity': filled,
            'price_per_unit': order.price_per_unit,
            'state': 'done',
            'tx_hash': _fake_hash(rnd),
            'confirmed_on': now - timedelta(
                days=rnd.randint(0, 30), hours=rnd.randint(0, 23)),
        })
        order.write({
            'state': verdict,
            'quantity_left': 0 if verdict == 'done'
            else round(order.quantity - filled, 3),
        })
        changed += 1
    return changed


def _mix_token_trades(env):
    if 'coop.token.trade' not in env:
        return 0
    Trade = env['coop.token.trade'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    reasons = [
        'Не хватило TON на комиссию сети',
        'Покупатель не подписал перевод за отведённое время',
        'Кошелёк продавца вернул токены: недостаточно на балансе',
        'Сеть отклонила транзакцию, сделка отменена',
    ]
    changed = 0
    for trade in Trade.search([('state', '=', 'done')], order='id'):
        verdict = _pick(_bucket('trade', trade.id), [
            (0.02, 'pending'), (0.05, 'sent'), (0.075, 'failed')])
        if not verdict:
            continue
        values = {'state': verdict}
        if verdict == 'pending':
            values.update({'tx_hash': False, 'confirmed_on': False})
        elif verdict == 'sent':
            values['confirmed_on'] = False
        else:
            values.update({
                'confirmed_on': False,
                'failure_reason': reasons[int(_bucket('why', trade.id) * 100)
                                          % len(reasons)],
            })
        trade.write(values)
        changed += 1
    return changed


# ── DEX ────────────────────────────────────────────────────────────────
def _mix_crypto_offers(env):
    if 'coop.crypto.offer' not in env:
        return 0
    Offer = env['coop.crypto.offer'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    Trade = env['coop.crypto.trade'].sudo()
    changed = 0
    for offer in Offer.search([('state', '=', 'active')], order='id'):
        traded = bool(Trade.search_count(
            [('offer_id', '=', offer.id), ('state', '=', 'done')], limit=1))
        bucket = _bucket('offer', offer.id)
        if traded:
            verdict = _pick(bucket, [(0.4, 'partial'), (0.65, 'done')])
        else:
            verdict = _pick(bucket, [(0.08, 'paused'), (0.16, 'closed')])
        if not verdict:
            continue
        values = {'state': verdict}
        top = offer.amount_max or offer.quantity_left
        if verdict == 'done':
            values['quantity_left'] = 0
        elif verdict == 'partial':
            values['quantity_left'] = round(
                top * (0.1 + 0.5 * _bucket('left', offer.id)), 8)
        offer.write(values)
        changed += 1
    return changed


def _mix_crypto_trades(env):
    if 'coop.crypto.trade' not in env:
        return 0
    Trade = env['coop.crypto.trade'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    changed = 0
    for trade in Trade.search([('state', '=', 'done')], order='id'):
        verdict = _pick(_bucket('ctrade', trade.id), [
            (0.02, 'cancelled'), (0.04, 'disputed'),
            (0.065, 'agreed'), (0.09, 'rub_sent')])
        if not verdict:
            continue
        trade.write({
            'state': verdict,
            'maker_confirmed': False,
            'taker_confirmed': verdict == 'rub_sent',
        })
        changed += 1
    return changed


# ── Бартер ─────────────────────────────────────────────────────────────
def _mix_barter_offers(env):
    if 'coop.barter.offer' not in env:
        return 0
    Offer = env['coop.barter.offer'].sudo().with_context(
        tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
    changed = 0
    for offer in Offer.search([('state', '=', 'active')], order='id'):
        if _bucket('barter', offer.id) < 0.06:
            offer.write({'state': 'draft'})
            changed += 1
    return changed

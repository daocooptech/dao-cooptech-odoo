# -*- coding: utf-8 -*-
"""Разовая чистка накопленного демо (владелец 07.10.2026: «Урезать до цели»).

До коммита d2c2589 загрузчик coop_demo на каждом -u добавлял выпуски
токенов (предел считал только созданные за прогон) и владения ЦФА (без
проверки «уже есть»). На боевой к 07.10 набралось 737 выпусков при цели
120 и 217 владений ЦФА при ~28 за прогон. Скрипт оставляет ровно то,
что оставил бы исправленный загрузчик:

* выпуски — первые TARGET по тому же плану, что в load_tokens (объявления
  в порядке id, две волны), остальные — вместе со сделками, эскроу,
  заявками и держателями;
* владения ЦФА — первые HOLDINGS по номеру (первый прогон).

Запуск (по умолчанию — без записи, только счёт):

    odoo-bin shell -c <conf> -d <база> --no-http < tools/trim_demo_overflow.py
    COOP_TRIM_APPLY=1 odoo-bin shell ...    # удалить и зафиксировать
"""
import os

TARGET = 120
HOLDINGS = 28
APPLY = os.environ.get('COOP_TRIM_APPLY') == '1'

Claim = env['coop.token.claim'].sudo()
Order = env['coop.token.order'].sudo()
Trade = env['coop.token.trade'].sudo()
Holding = env['coop.token.holding'].sudo()
Escrow = env['coop.token.escrow'].sudo()
Resource = env['coop.resource'].sudo()
CfaHolding = env['coop.cfa.holding'].sudo()


def counts():
    return {name: model.search_count([]) for name, model in (
        ('выпуски', Claim), ('заявки', Order), ('сделки', Trade),
        ('держатели', Holding), ('эскроу', Escrow), ('владения ЦФА', CfaHolding))}


before = counts()

resources = Resource.search([
    ('state', '=', 'published'),
    ('listing_type', '=', 'offer'),
    ('owner_id.coop_verified', '=', True),
], order='id')
by_key = {c.import_key: c for c in Claim.search([('import_key', '=like', 'tokens#%')])}
keep = Claim.browse()
for wave in (0, 1):
    for resource in resources:
        if len(keep) >= TARGET:
            break
        claim = by_key.get('tokens#%s.%s' % (resource.id, wave))
        if claim:
            keep |= claim
drop = Claim.search([('import_key', '=like', 'tokens#%'), ('id', 'not in', keep.ids)])

trades = Trade.search([('claim_id', 'in', drop.ids)])
escrow = Escrow.search([('trade_id', 'in', trades.ids)])
orders = Order.search([('claim_id', 'in', drop.ids)])
holders = Holding.search([('claim_id', 'in', drop.ids)])
cfa_drop = CfaHolding.search([], order='id')[HOLDINGS:]

print('до:', before)
print('оставляю выпусков %s, удаляю %s (сделок %s, эскроу %s, заявок %s, держателей %s); '
      'владений ЦФА удаляю %s' % (len(keep), len(drop), len(trades), len(escrow),
                                   len(orders), len(holders), len(cfa_drop)))

if APPLY:
    escrow.unlink()
    trades.unlink()
    orders.unlink()
    holders.unlink()
    if 'coop_token_claim_id' in Resource._fields:
        Resource.search([('coop_token_claim_id', 'in', drop.ids)]).write(
            {'coop_token_claim_id': False})
    drop.unlink()
    cfa_drop.unlink()
    env.cr.commit()
    print('после:', counts())
else:
    env.cr.rollback()
    print('пробный прогон: ничего не записано (COOP_TRIM_APPLY=1 — записать)')

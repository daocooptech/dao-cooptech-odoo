# -*- coding: utf-8 -*-
"""Валюта приёма — рубль у всех, у кого стоял доллар по умолчанию.

Поле заполнилось при установке валютой компании, а у неё тогда ещё был
доллар чистого Odoo: у всех участников, и у ТСН в России, валютой приёма
стоял USD (владелец 27.10.2026: «измени валюту, это важно»). Сознательно
выбранных валют, кроме доллара, не трогаем.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rub = env.ref('base.RUB', raise_if_not_found=False)
    usd = env.ref('base.USD', raise_if_not_found=False)
    if not rub or not usd:
        return
    if not rub.active:
        rub.active = True
    cr.execute('UPDATE res_partner SET coop_payout_currency_id = %s '
               'WHERE coop_payout_currency_id = %s', (rub.id, usd.id))

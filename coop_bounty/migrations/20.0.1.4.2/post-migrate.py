# -*- coding: utf-8 -*-
"""Тикеры токенов проектов — латиницей (владелец 17.11.2026).

«почему токены русскими буквами? смотри мировые стандарты»: тикер —
как на биржах и в ERC-20 (BTC, ETH, USDT). Наш проект платит токенами
платформы — их тикер COOP (модуль coop_tokens). Остальным русские
обозначения переводятся в латиницу по первым буквам названия.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_bounty.models.coop_crowd import TICKER_RE


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True, 'active_test': False})
    Project = env['coop.project']
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    if ours and ours.coop_token_symbol != 'COOP':
        clash = Project.search([('coop_token_symbol', '=', 'COOP'), ('id', '!=', ours.id)])
        clash.write({'coop_token_symbol': False})
        ours.coop_token_symbol = 'COOP'
    for project in Project.search([('coop_token_symbol', '!=', False)], order='id'):
        if not TICKER_RE.match(project.coop_token_symbol.strip().upper()):
            project.coop_token_symbol = False
            project.coop_token_symbol = Project._coop_ticker_from(project.name)

# -*- coding: utf-8 -*-
"""Журнал сведений биржи — для дашборда «Биржа» (решение 420, слой 2).

Обмены DEX участник видит только свои (правило записей `coop.crypto.trade`),
а общий рынок платформы открыт в журнале исполнений `coop.match.fill` —
его читают все. Но рынок там записан ключом (`dex:BTC:btc`, `token:588`),
а сумма сделки не хранится вовсе: сводная таблица движка ни подписи, ни
оборота из него не соберёт. Три хранимых поля: рынок так, как его пишет
экран DEX («BTC», «USDT · TON», предмет выпуска токенов), раздел биржи и
оборот в рублях.
"""
from odoo import api, fields, models

SECTIONS = [('dex', 'DEX биржа'), ('token', 'Токеномика')]


class CoopMatchFill(models.Model):
    _inherit = 'coop.match.fill'

    coop_section = fields.Selection(SECTIONS, string='Раздел биржи',
                                    compute='_compute_coop_market', store=True)
    coop_market_label = fields.Char(string='Пара', compute='_compute_coop_market', store=True)
    coop_turnover = fields.Float(string='Оборот, ₽', digits=(16, 2), aggregator='sum',
                                 compute='_compute_coop_market', store=True)

    @api.depends('market', 'quantity', 'price')
    def _compute_coop_market(self):
        networks = {n.code: n.name for n in self.env['coop.wallet.network'].sudo().search([])}
        Claim = self.env['coop.token.claim'].sudo()
        for fill in self:
            parts = (fill.market or '').split(':')
            section = parts[0] if parts[0] in dict(SECTIONS) else False
            label = fill.market
            if section == 'dex' and len(parts) == 3:
                asset, network = parts[1], networks.get(parts[2], parts[2])
                # Как на экране DEX: одна монета в разных сетях — разные
                # рынки, но имя сети пишется только у USDT.
                label = '%s · %s' % (asset, network) if asset == 'USDT' else asset
            elif section == 'token' and len(parts) == 2 and parts[1].isdigit():
                claim = Claim.browse(int(parts[1])).exists()
                label = claim.resource_id.name or label if claim else label
            fill.coop_section = section
            fill.coop_market_label = label
            fill.coop_turnover = (fill.quantity or 0.0) * (fill.price or 0.0)

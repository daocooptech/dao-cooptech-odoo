# -*- coding: utf-8 -*-
"""Способ «TON» стал «Токенами» с выбором сети и токена (владелец
24 сентября 2026). Прежние подарки в TON — это токен TON в сети TON."""


def migrate(cr, version):
    cr.execute("""
        UPDATE coop_wall_thanks t
           SET channel = 'token',
               token = 'TON',
               currency = 'TON',
               network_id = (SELECT id FROM coop_wallet_network WHERE code = 'ton' LIMIT 1)
         WHERE t.channel = 'ton'
    """)

# -*- coding: utf-8 -*-
"""Порог автовыплаты заработал: пустой порог у счёта с подключением банка
значил бы «подписывают все» и остановил бы выплаты. Ставим тот же порог,
что у наполнения; менять — в карточке счёта."""


def migrate(cr, version):
    cr.execute("""
        UPDATE coop_nominal_account
           SET auto_payout_limit = 100000
         WHERE adapter != 'manual' AND COALESCE(auto_payout_limit, 0) = 0
    """)

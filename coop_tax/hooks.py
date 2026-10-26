# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Узлы выбирают по-разному, и выплаты, проведённые до модуля, получают
    свой НДФЛ.

    Каждый четвёртый кооператив с паевыми счетами выбрал «только сверх
    внесённого» (решение 513): на платформе видны оба варианта и разница
    в «на руки». Остальные — по умолчанию, со всей суммы.
    """
    accounts = env['coop.share.account'].search([])
    coops = accounts.mapped('cooperative_id').sorted('id')
    coops.filtered(lambda c: c.id % 4 == 0).write({'coop_ndfl_share_base': 'excess'})
    moves = env['coop.share.move'].search([('kind', 'in', ('payout', 'return'))])
    moves._coop_tax_fill()

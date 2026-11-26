# -*- coding: utf-8 -*-
"""№ 454, 26.11: у сообществ прикрепляется то же, что у людей и организаций.

Проект — 60 % записей, сообщество — 40 %, страницы людей и организаций —
20 %; запись берётся из уместных этой стене каталогов (`coop_wall`,
`models/wall_attach.py`). Уже прикреплённое не трогается.
"""
import logging
import random

from odoo import SUPERUSER_ID, api

SHARE = {'coop.community': 0.4, 'coop.project': 0.3}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Message = env['mail.message'].sudo()
    rnd = random.Random(20261127)
    posts = Message.search([
        ('message_type', '=', 'comment'), ('model', 'in', list(SHARE)),
        ('coop_rec_model', '=', False)], order='id')
    pools = {}
    attached = 0
    for post in posts:
        if rnd.random() > SHARE[post.model]:
            continue
        key = (post.model, post.res_id)
        if key not in pools:
            pool = []
            for _k, _l, target, domain in Message._coop_attach_sources(*key):
                pool += [(target, rid) for rid in
                         env[target].sudo().search(domain, limit=30).ids]
            pools[key] = pool
        if not pools[key]:
            continue
        target, rid = rnd.choice(pools[key])
        post.write({'coop_rec_model': target, 'coop_rec_id': rid})
        attached += 1
    logging.getLogger(__name__).info('Прикреплено записей к постам: %s', attached)

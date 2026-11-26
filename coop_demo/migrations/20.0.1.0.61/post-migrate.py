# -*- coding: utf-8 -*-
"""№ 454: у части записей стен — прикреплённая запись из каталогов.

Проект — 60 % записей, сообщество — 40 %, страницы людей и организаций —
20 %; запись берётся из уместных этой стене каталогов (`coop_wall`,
`models/wall_attach.py`). Уже прикреплённое не трогается.
"""
import logging
import random

from odoo import SUPERUSER_ID, api

SHARE = {'coop.project': 0.6, 'coop.community': 0.4, 'res.partner': 0.2}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Message = env['mail.message'].sudo()
    rnd = random.Random(20261126)
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

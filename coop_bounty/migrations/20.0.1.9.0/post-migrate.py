# -*- coding: utf-8 -*-
"""Экономика COOP — по решению 700: фонд растёт с каждой новой задачей."""
from markupsafe import Markup

from odoo import SUPERUSER_ID, api

OLD = '100 000 токенов на три месяца; задача публикуется, только когда вся её сумма отложена в фонде.'
NEW = 'первоначально 100 000 токенов, дальше фонд растёт на оценку каждой новой задачи; задачу отменили — выпущенное под неё изымается. Публикуется задача, только когда вся её сумма отложена в фонде.'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    text = str(ours.coop_token_economy or '') if ours else ''
    for space in (' ', ' '):
        old = OLD.replace('100 000', '100%s000' % space)
        if old in text:
            ours.coop_token_economy = Markup(text.replace(old, NEW))
            break

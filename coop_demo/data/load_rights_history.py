# -*- coding: utf-8 -*-
"""История прав собственности у материальных ресурсов (№ 389).

Владелец 28.10.2026: в аренде нужна история прав **собственности**, а не
аренды. Аренда права не передаёт и в журнал не попадает — в нём только
постановка на учёт, продажа, дар и обмен. Но в демо у почти каждой вещи
журнал состоял из одной строки «Поставлен на учёт», и вкладка выглядела
пустой. Здесь цепочки достраиваются: у вещи были прежние владельцы, и
она дошла до нынешнего через продажи, дары и обмены.

Цепочка пересобирается целиком (хэши зависят от порядка), поэтому
трогаются только ресурсы, у которых журнал ещё состоит из одной
постановки на учёт: повторный запуск ничего не меняет. У вещей, которые
сдают («в пользование»), история есть всегда — их и смотрят в аренде.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Доля вещей «в собственность» с историей; сдаваемые — все.
SHARE_WITH_HISTORY = 0.6
# Как менялся владелец: чаще всего продажа.
KINDS = ['sale'] * 6 + ['gift'] * 1 + ['exchange'] * 2 + ['batch'] * 1


def load_rights_history(env):
    Resource = env['coop.resource'].sudo()
    Transfer = env['coop.resource.transfer'].sudo()
    Partner = env['res.partner'].sudo()
    if 'ownership_kind' not in Resource._fields:
        return 0
    people = Partner.search([('coop_is_participant', '=', True)], order='id')
    if len(people) < 5:
        return 0

    rnd = random.Random(20261109)
    now = fields.Datetime.now()
    rebuilt = 0
    resources = Resource.search([
        ('listing_type', '=', 'offer'), ('resource_type', '=', 'material'),
        ('state', '=', 'published'), ('owner_id', '!=', False)], order='id')
    for resource in resources:
        history = Transfer.search([('resource_id', '=', resource.id)])
        if len(history) != 1 or history.kind != 'registered':
            continue
        if (resource.ownership_kind != 'use'
                and rnd.random() > SHARE_WITH_HISTORY):
            continue
        owner = resource.owner_id
        prior = []
        for _step in range(rnd.randint(1, 3)):
            candidate = people[rnd.randrange(len(people))]
            last = prior[-1] if prior else owner
            if candidate != owner and candidate != last:
                prior.append(candidate)
        if not prior:
            continue
        # Первый — тот, кто поставил вещь на учёт; последний шаг — к
        # нынешнему владельцу. Даты растут, последняя — до сегодняшнего дня.
        chain = prior + [owner]
        steps = len(chain)
        start = now - timedelta(days=rnd.randint(300 * steps // 2 + 60, 1500))
        span = (now - start).days - 5
        with env.cr.savepoint():
            env.cr.execute(
                'DELETE FROM coop_resource_transfer WHERE resource_id = %s',
                [resource.id])
            Transfer.invalidate_model()
            Transfer._coop_append(resource, 'registered', chain[0], start)
            for number in range(1, steps):
                moment = start + timedelta(days=span * number // steps
                                           + rnd.randint(1, 20))
                kind = ('sale' if number == steps - 1 and resource.price
                        else rnd.choice(KINDS))
                Transfer._coop_append(
                    resource, kind, chain[number], moment,
                    from_partner=chain[number - 1])
        rebuilt += 1
    _logger.info('История прав: достроена у %s ресурсов', rebuilt)
    return rebuilt

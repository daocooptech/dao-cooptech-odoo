# -*- coding: utf-8 -*-
"""Даты дружбы и подписок, заведённых загрузчиком (владелец 19.10.2026:
«полноценный пример аналитики»).

Загрузчик заводил дружбу и подписки на людей одним прогоном, и у всех
760 дружб и 8 442 подписок стояла дата этого прогона. Аналитика «Моего
аккаунта» видела в одном месяце всех друзей разом, а за прошлые — ни
одного: мини-графики плиток «друзей» и «подписчиков» и график активности
врали. Здесь каждой такой записи ставится дата с 8 января 2024 по вчера,
гуще к сегодняшнему дню — как растёт живая платформа.

Трогаются только записи загрузчика (`create_uid` = суперпользователь):
дружба и подписки, заведённые людьми на экране, остаются со своими
датами. Дата выводится из номера записи, поэтому повторный прогон ставит
то же самое.
"""
import logging
import random
from datetime import datetime, timedelta

from odoo import SUPERUSER_ID, fields

_logger = logging.getLogger(__name__)

START = datetime(2024, 1, 8, 9, 0)


def _spread(cr, table, where, seed):
    cr.execute('SELECT id FROM %s WHERE create_uid = %%s AND %s' % (table, where),
               (SUPERUSER_ID,))
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        return 0
    end = fields.Datetime.now() - timedelta(days=1)
    span = (end - START).total_seconds()
    values = []
    for record_id in ids:
        rnd = random.Random('%s:%s' % (seed, record_id))
        when = START + timedelta(seconds=int(span * (rnd.random() ** 0.6)))
        values.append("(%d, '%s'::timestamp)" % (record_id, when.strftime('%Y-%m-%d %H:%M:%S')))
    for chunk in range(0, len(values), 2000):
        cr.execute(
            'UPDATE %s AS t SET create_date = v.at, write_date = v.at '
            'FROM (VALUES %s) AS v(id, at) WHERE t.id = v.id AND t.create_date <> v.at'
            % (table, ', '.join(values[chunk:chunk + 2000])))
    return len(ids)


def spread_social_dates(env):
    cr = env.cr
    friends = _spread(cr, 'coop_friendship', "state = 'accepted'", 'friendship') \
        if 'coop.friendship' in env else 0
    followers = _spread(cr, 'mail_followers', "res_model = 'res.partner'", 'follower')
    env.invalidate_all()
    _logger.info('Даты дружбы и подписок разнесены: дружб %s, подписок %s', friends, followers)

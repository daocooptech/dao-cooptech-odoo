# -*- coding: utf-8 -*-
"""Извещения — из того, что на платформе уже произошло.

Решение 375 от 22 сентября 2026: **не выдумывать события, а породить
извещения из случившегося** — сделок, вкладов в проекты, откликов на
вакансии, приёмов в членство, заказов в закупках.

Отчего так, а не списком придуманных строк. Извещение, сочинённое на
ровном месте, ведёт в пустоту: человек нажимает на него и не находит
записи. Порождённое из записи — ведёт на неё, и разброс дат получается
настоящий, а не расставленный руками.

Состояния обязаны быть разными: прочитанные и непрочитанные, свежие и
давние, со ссылкой и без. Раздел, где всё одинаковое, не показывает ни
счётчика непрочитанного, ни порядка, ни поведения под нагрузкой.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Сколько извещений набираем. Правило 100–200 распространяется и на
# разделы-действия (решение 254), а извещения — как раз такой раздел.
TARGET = 260

# Доля уже прочитанных. Не половина: непрочитанных должно быть заметно
# меньше, иначе счётчик у колокольчика выглядит поломанным.
READ_SHARE = 0.72


def _text(kind, record, me):
    """Что сказать человеку про эту запись.

    Текст собирается из самой записи, а не берётся из списка заготовок:
    «по вашей сделке» без номера сделки — это шум, а не извещение.
    """
    name = record.display_name or ''
    if kind == 'deal':
        return ('Сделка <b>%s</b> перешла в новое состояние. '
                'Проверьте, не ждут ли действия от вас.' % name)
    if kind == 'project':
        return ('В проекте <b>%s</b> что-то изменилось: принят вклад или '
                'пройдена веха.' % name)
    if kind == 'vacancy':
        return 'На вакансию <b>%s</b> откликнулись.' % name
    if kind == 'resource':
        return 'По объявлению <b>%s</b> пришёл отклик.' % name
    if kind == 'org':
        return ('Ваше участие в организации <b>%s</b> изменилось.' % name)
    if kind == 'community':
        return 'В сообществе <b>%s</b> новое событие.' % name
    if kind == 'auction':
        return 'По торгам <b>%s</b> появилась новая ставка.' % name
    if kind == 'wallet':
        return 'По кошельку прошла операция: <b>%s</b>.' % name
    return 'Событие по записи <b>%s</b>.' % name


def _sources(env):
    """Откуда берём события: вид извещения, модель, поле получателя.

    Получатель берётся у самой записи — тот, кого событие касается.
    Рассылать извещения всем подряд значило бы завести раздел, который
    человек закроет и больше не откроет.
    """
    return [
        ('deal', 'coop.deal', ('party_a_id', 'party_b_id')),
        ('project', 'coop.project.contribution', ('partner_id',)),
        ('vacancy', 'coop.vacancy.application', ('partner_id',)),
        ('resource', 'coop.resource.respond', ('partner_id',)),
        ('org', 'coop.membership', ('partner_id',)),
        ('community', 'coop.community.member', ('partner_id',)),
        ('auction', 'coop.auction.bid', ('partner_id',)),
        ('wallet', 'coop.wallet.movement', ('partner_id',)),
    ]


def load_notifications(env, target=TARGET):
    Notification = env['coop.notification'].sudo()
    if Notification.search_count([]) >= target // 2:
        _logger.info('Извещения: уже наполнены, пропускаю')
        return 0

    rnd = random.Random(20260923)
    now = fields.Datetime.now()
    collected_value = []

    for kind, model, owner_fields in _sources(env):
        if model not in env:
            continue
        Model = env[model].sudo()
        available = [f for f in owner_fields if f in Model._fields]
        if not available:
            continue
        records = Model.search([], limit=target, order='id desc')
        for record in records:
            for field in available:
                who = record[field]
                if not who or len(who) != 1:
                    continue
                collected_value.append((kind, record, who))

    if not collected_value:
        _logger.warning('Извещения: событий на платформе не нашлось')
        return 0

    rnd.shuffle(collected_value)
    collected_value = collected_value[:target]

    lines = []
    for kind, record, who in collected_value:
        # Давность: от часа до полугода. Извещения одного дня не
        # показывают ни порядка, ни того, как раздел выглядит, когда в
        # нём накопилось.
        age_hours = rnd.choice([
            rnd.randint(1, 20),
            rnd.randint(24, 24 * 14),
            rnd.randint(24 * 14, 24 * 180),
        ])
        when = now - timedelta(hours=age_hours)
        # Свежие чаще непрочитаны — так и бывает.
        read_chance = READ_SHARE if age_hours > 48 else 0.25
        is_read = rnd.random() < read_chance
        lines.append({
            'partner_id': who.id,
            'kind': kind,
            'body': _text(kind, record, who),
            'res_model': record._name,
            'res_id': record.id,
            'is_read': is_read,
            'read_on': when + timedelta(hours=rnd.randint(1, 12))
            if is_read else False,
            'create_date': when,
        })

    created = Notification.create(lines)

    # Дату создания движок ставит свою — переписываем запросом, иначе все
    # извещения окажутся одной минуты и раздел будет выглядеть
    # сгенерированным ровно тем, чем он и является.
    for line, record in zip(lines, created):
        env.cr.execute(
            'UPDATE coop_notification SET create_date = %s WHERE id = %s',
            (line['create_date'], record.id))
    env.invalidate_all()

    unread = sum(1 for line in lines if not line['is_read'])
    _logger.info('Извещения: создано %s, из них непрочитанных %s',
                 len(created), unread)
    return len(created)

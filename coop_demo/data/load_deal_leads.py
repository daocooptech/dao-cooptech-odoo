# -*- coding: utf-8 -*-
"""Обращения людей — первая стадия сделки (решение 451).

Лид человека — сделка в стадии «Обращение». Заводят их сами участники
своими правами: откликаются на чужое объявление о ресурсе тем же
мастером, что и кнопка «Откликнуться» в каталоге. Дальше владелец
объявления (человек или тот, кому организация поручила «Сделки»)
отвечает: часть обращений принимает в переговоры, часть отклоняет, часть
откликнувшиеся отменяют сами; остальные ждут ответа.

Повторяемо: ключ — номер обращения; уже заведённые пропускаются. Жребий —
от номера обращения.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

TARGET = 140
NOTES = [
    'Готов забрать на этой неделе, если ещё актуально.',
    'Подскажите, возможна ли доставка?',
    'Интересует партия побольше — обсудим цену?',
    'Можно посмотреть вживую перед сделкой?',
    'Нужны документы и фото, пришлите, пожалуйста.',
    'Рассмотрю обмен, если вам удобно.',
    'Оплата по безналу через организацию — подойдёт?',
    'Срок — до конца месяца, раньше не нужно.',
    '',
]
# Тестовые учётки владельца не откликаются: их видно в демо как настоящих.
TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')


def _answering_user(env, owner):
    """Кто отвечает на обращение за владельца объявления."""
    if not owner.is_company:
        return owner.user_ids.filtered('active')[:1]
    return env['coop.membership'].sudo().search([
        ('organization_id', '=', owner.id), ('state', '=', 'active'),
        ('power_ids.code', '=', 'deal')]).partner_id.user_ids.filtered('active')[:1]


def load_deal_leads(env, target=TARGET):
    if 'coop.resource.respond' not in env:
        return 0
    Deal = env['coop.deal'].sudo()
    have = Deal.search_count([('import_key', '=like', 'lead#%')])
    if have >= target:
        _logger.info('Обращения: уже %s, пропускаю', have)
        return 0
    people = env['res.users'].sudo().search([
        ('partner_id.coop_is_participant', '=', True),
        ('partner_id.is_company', '=', False),
        ('partner_id.name', 'not in', TEST_NAMES)], order='id')
    listings = env['coop.resource'].sudo().search([
        ('state', '=', 'published')], order='id')
    if not people or not listings:
        return 0
    made = stats_neg = stats_lost = stats_own = skipped = 0
    now = datetime.now()
    number = 0
    while have + made < target and number < target * 4:
        number += 1
        key = 'lead#%s' % number
        if Deal.search_count([('import_key', '=', key)]):
            continue
        rnd = random.Random(20261008 + number)
        listing = listings[rnd.randrange(len(listings))]
        buyer = people[rnd.randrange(len(people))]
        answering = _answering_user(env, listing.owner_id)
        if not answering or buyer.partner_id == listing.owner_id \
                or buyer == answering:
            skipped += 1
            continue
        try:
            with env.cr.savepoint():
                wizard = env['coop.resource.respond'].with_user(buyer).create({
                    'resource_id': listing.id,
                    'note': rnd.choice(NOTES),
                })
                action = wizard.action_respond()
                deal = Deal.browse(action['res_id'])
                deal.import_key = key
                roll = rnd.random()
                if roll < 0.35:
                    deal.with_user(answering).action_negotiate()
                    stats_neg += 1
                elif roll < 0.52:
                    deal.with_user(answering).action_cancel()
                    stats_lost += 1
                elif roll < 0.58:
                    deal.with_user(buyer).action_cancel()
                    stats_own += 1
        except Exception as error:  # чужое объявление закрыто от человека и т. п.
            _logger.debug('Обращение %s пропущено: %s', key, error)
            skipped += 1
            continue
        # Разброс дат: обращения шли последние два с половиной месяца.
        when = now - timedelta(days=rnd.randint(0, 75), hours=rnd.randint(0, 23))
        env.cr.execute('UPDATE coop_deal SET create_date = %s WHERE id = %s',
                       (when, deal.id))
        made += 1
    Deal.invalidate_model(['create_date'])
    _logger.info('Обращения: заведено %s (в переговоры %s, отклонено %s, '
                 'отменено самими %s), пропущено %s',
                 made, stats_neg, stats_lost, stats_own, skipped)
    return made

# -*- coding: utf-8 -*-
"""Обращения из разговоров — «Написать владельцу» и «Показать номер»
(задача 412, владелец 10.11.2026).

Заводятся тем же путём, что и кнопки на объявлении: от имени
обратившегося, `coop.deal._coop_inquiry_for`. Половина — по объявлениям
dashkevich (ему пишут и звонят), половина — его собственные обращения по
чужим объявлениям: раздел «Обращения» показывают под ним (решение 443),
и пустая доска там была бы неправдой о разделе.

Дальше — как в жизни: часть берут в переговоры, часть из переговоров
согласуют, часть отклоняют или отменяют сами, остальные ждут — и среди
них зависшие, без ответа больше месяца. Первая реплика ложится в
переписку обращения.

Повторяемо: ключ — номер обращения (`inq#N`), жребий — от номера.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

TARGET = 130
OWNER_LOGIN = 'dashkevich'
FIRST_WORDS = [
    'Здравствуйте! Объявление ещё актуально?',
    'Добрый день. Можно посмотреть на этой неделе?',
    'Подскажите, торг уместен?',
    'Интересует, есть ли доставка до моего города.',
    'Здравствуйте, нужен на два месяца — подойдёт?',
    'Добрый день! Рассмотрите обмен на мою технику?',
    'Можно оплатить через организацию по счёту?',
    'Пришлите, пожалуйста, ещё фото и документы.',
    'Сколько возьмёте за партию побольше?',
    'Когда удобно созвониться?',
]
TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')


def _answering_user(env, owner):
    if not owner.is_company:
        return owner.user_ids.filtered('active')[:1]
    return env['coop.membership'].sudo().search([
        ('organization_id', '=', owner.id), ('state', '=', 'active'),
        ('power_ids.code', '=', 'deal')]).partner_id.user_ids.filtered('active')[:1]


def _say(deal, user, text):
    channel = deal._coop_channels('deal')[:1] if hasattr(deal, '_coop_channels') else False
    if not channel:
        return
    channel.with_user(user).sudo().message_post(
        body=text, author_id=user.partner_id.id,
        message_type='comment', subtype_xmlid='mail.mt_comment')


def mark_respond_sources(env):
    """Отклики прежнего наполнения (`lead#`) — источник «Отклик»."""
    env.cr.execute("""UPDATE coop_deal SET inquiry_source = 'respond'
                       WHERE import_key LIKE 'lead#%%' AND inquiry_source IS NULL""")


def load_inquiries(env, target=TARGET):
    Deal = env['coop.deal'].sudo()
    me = env['res.users'].sudo().search([('login', '=', OWNER_LOGIN)], limit=1)
    if not me or not hasattr(Deal, '_coop_inquiry_for'):
        return 0
    have = Deal.search_count([('import_key', '=like', 'inq#%')])
    if have >= target:
        _logger.info('Обращения из разговоров: уже %s, пропускаю', have)
        return 0
    people = env['res.users'].sudo().search([
        ('partner_id.coop_is_participant', '=', True),
        ('partner_id.is_company', '=', False),
        ('partner_id.name', 'not in', TEST_NAMES),
        ('id', '!=', me.id)], order='id')
    mine = env['coop.resource'].sudo().search([
        ('state', '=', 'published'), ('owner_id', '=', me.partner_id.id)], order='id')
    others = env['coop.resource'].sudo().search([
        ('state', '=', 'published'), ('owner_id', '!=', me.partner_id.id),
        ('owner_id.is_company', '=', False)], order='id')
    if not people or not mine or not others:
        return 0
    stats = dict(made=0, lead=0, draft=0, agreed=0, lost=0, skipped=0)
    now = datetime.now()
    number = 0
    while have + stats['made'] < target and number < target * 4:
        number += 1
        key = 'inq#%s' % number
        if Deal.search_count([('import_key', '=', key)]):
            continue
        rnd = random.Random(20261111 + number)
        if number % 2:
            listing = mine[rnd.randrange(len(mine))]
            asker = people[rnd.randrange(len(people))]
        else:
            listing = others[rnd.randrange(len(others))]
            asker = me
        answering = _answering_user(env, listing.owner_id)
        if not answering or answering == asker:
            stats['skipped'] += 1
            continue
        source = 'call' if rnd.random() < 0.3 else 'message'
        try:
            with env.cr.savepoint():
                deal = Deal.with_user(asker)._coop_inquiry_for(
                    listing.with_user(asker), source).sudo()
                if not deal or deal.import_key:
                    stats['skipped'] += 1
                    continue
                deal.import_key = key
                if source == 'message':
                    _say(deal, asker, rnd.choice(FIRST_WORDS))
                roll = rnd.random()
                if roll < 0.30:
                    deal.with_user(answering).action_negotiate()
                    _say(deal, answering, 'Да, актуально. Давайте обсудим условия.')
                    stats['draft'] += 1
                elif roll < 0.42:
                    deal.with_user(answering).action_negotiate()
                    env['coop.deal.line'].sudo().create({
                        'deal_id': deal.id, 'name': listing.name,
                        'quantity': 1, 'price_unit': deal.amount or listing.price or 1000})
                    try:
                        with env.cr.savepoint():
                            deal.with_user(answering).action_agree()
                            stats['agreed'] += 1
                    except Exception:  # личность стороны не подтверждена
                        stats['draft'] += 1
                elif roll < 0.62:
                    who = answering if rnd.random() < 0.6 else asker
                    deal.with_user(who).action_cancel()
                    stats['lost'] += 1
                else:
                    stats['lead'] += 1
        except Exception as error:
            _logger.debug('Обращение %s пропущено: %s', key, error)
            stats['skipped'] += 1
            continue
        # Обращения шли последние три месяца; ждущие ответа старше
        # месяца — зависшие.
        when = now - timedelta(days=rnd.randint(0, 90), hours=rnd.randint(0, 23))
        env.cr.execute('UPDATE coop_deal SET create_date = %s, funnel_date = %s '
                       'WHERE id = %s AND signed_on IS NULL', (when, when.date(), deal.id))
        stats['made'] += 1
    Deal.invalidate_model(['create_date', 'funnel_date'])
    _logger.info('Обращения из разговоров: %s', stats)
    return stats['made']


SKILL_WORDS = [
    'Здравствуйте! Свободны на следующей неделе?',
    'Добрый день, нужна консультация — сколько стоит час?',
    'Можете взяться за небольшой заказ в выходные?',
    'Подскажите, работаете с организациями по договору?',
    'Нужен выезд на объект, когда удобно?',
    'Сколько займёт работа под ключ?',
]
SKILL_TARGET = 110
# Входящих к единственному навыку dashkevich — несколько, как у живого
# исполнителя за квартал. Было «каждое третье»: 38 одинаковых обращений
# «Электромонтажник, 70 000» к одному человеку (№ 418, владелец 11.11:
# «это не по-настоящему»).
SKILL_MINE_MAX = 6


def _skill_amount(offer, rnd):
    """Сумма обращения — объём работы, а не одна ставка на всех: ставка
    навыка — за час или за работу, и каждому нужно своё."""
    rate = offer.rate or 0.0
    if not rate:
        return 0.0
    amount = rate * rnd.choice((0.5, 0.75, 1, 1, 1.5, 2, 3))
    step = 500 if amount >= 5000 else 100
    return max(step, round(amount / step) * step)


def trim_skill_inquiries(env, keep=SKILL_MINE_MAX):
    """Убрать лишние демо-обращения к навыку dashkevich, оставив `keep`
    самых разных по состоянию. Только демо (`sinq#`), только не начатые."""
    Deal = env['coop.deal'].sudo()
    me = env['res.users'].sudo().search([('login', '=', OWNER_LOGIN)], limit=1)
    if not me:
        return 0
    deals = Deal.search([('import_key', '=like', 'sinq#%'),
                         ('skill_offer_id.partner_id', '=', me.partner_id.id)], order='id')
    if len(deals) <= keep:
        return 0
    kept = deals.browse()
    for state in ('lead', 'draft', 'cancelled', 'lead', 'draft', 'lead'):
        pick = (deals - kept).filtered(lambda d: d.state == state)[:1]
        kept |= pick
    kept |= (deals - kept)[:max(0, keep - len(kept))]
    extra = (deals - kept).filtered(lambda d: d.state in ('lead', 'draft', 'cancelled'))
    env['mail.activity'].sudo().search([
        ('res_model', '=', 'coop.deal'), ('res_id', 'in', extra.ids)]).unlink()
    count = len(extra)
    extra.unlink()
    _logger.info('Обращения к навыку dashkevich: убрано %s, оставлено %s', count, len(kept))
    return count


def vary_skill_amounts(env):
    """Разные суммы у уже заведённых демо-обращений по навыкам: раньше
    у всех обращений к одному навыку стояла одна ставка."""
    Deal = env['coop.deal'].sudo()
    deals = Deal.search([('import_key', '=like', 'sinq#%'),
                         ('state', 'in', ('lead', 'draft', 'cancelled'))])
    for deal in deals:
        amount = _skill_amount(deal.skill_offer_id, random.Random(20261111 + deal.id))
        if amount and amount != deal.amount:
            deal.amount = amount
    return len(deals)


def load_skill_inquiries(env, target=SKILL_TARGET):
    """Обращения по предложениям навыков (владелец 11.11.2026: обращения
    — в каждом разделе, где уместны). К единственному предложению
    dashkevich — не больше `SKILL_MINE_MAX`, остальное — его обращения к
    исполнителям. Ключ `sinq#N`."""
    Deal = env['coop.deal'].sudo()
    me = env['res.users'].sudo().search([('login', '=', OWNER_LOGIN)], limit=1)
    if not me or not hasattr(Deal, '_coop_skill_inquiry_for'):
        return 0
    have = Deal.search_count([('import_key', '=like', 'sinq#%')])
    if have >= target:
        return 0
    Offer = env['coop.skill.offer'].sudo()
    mine = Offer.search([('state', '=', 'published'), ('partner_id', '=', me.partner_id.id)])
    others = Offer.search([('state', '=', 'published'), ('partner_id', '!=', me.partner_id.id),
                           ('partner_id.is_company', '=', False)], order='id')
    people = env['res.users'].sudo().search([
        ('partner_id.coop_is_participant', '=', True),
        ('partner_id.is_company', '=', False),
        ('partner_id.name', 'not in', TEST_NAMES), ('id', '!=', me.id)], order='id')
    if not others or not people:
        return 0
    stats = dict(made=0, lead=0, draft=0, lost=0, skipped=0)
    now = datetime.now()
    number = 0
    while have + stats['made'] < target and number < target * 4:
        number += 1
        key = 'sinq#%s' % number
        if Deal.search_count([('import_key', '=', key)]):
            continue
        rnd = random.Random(20261112 + number)
        to_me = Deal.search_count([('import_key', '=like', 'sinq#%'),
                                   ('skill_offer_id', 'in', mine.ids)]) if mine else 0
        if mine and number % 3 == 0 and to_me < SKILL_MINE_MAX:
            offer, asker = mine[0], people[rnd.randrange(len(people))]
        else:
            offer, asker = others[rnd.randrange(len(others))], me
        answering = offer.partner_id.user_ids.filtered('active')[:1]
        if not answering or answering == asker:
            stats['skipped'] += 1
            continue
        source = 'call' if rnd.random() < 0.3 else 'message'
        try:
            with env.cr.savepoint():
                deal = Deal.with_user(asker)._coop_skill_inquiry_for(
                    offer.with_user(asker), source).sudo()
                if not deal or deal.import_key:
                    stats['skipped'] += 1
                    continue
                deal.import_key = key
                deal.amount = _skill_amount(offer, rnd)
                if source == 'message':
                    _say(deal, asker, rnd.choice(SKILL_WORDS))
                roll = rnd.random()
                if roll < 0.35:
                    deal.with_user(answering).action_negotiate()
                    _say(deal, answering, 'Да, могу. Давайте обсудим объём и сроки.')
                    stats['draft'] += 1
                elif roll < 0.55:
                    deal.with_user(answering if rnd.random() < 0.6 else asker).action_cancel()
                    stats['lost'] += 1
                else:
                    stats['lead'] += 1
        except Exception as error:
            _logger.debug('Обращение %s пропущено: %s', key, error)
            stats['skipped'] += 1
            continue
        when = now - timedelta(days=rnd.randint(0, 90), hours=rnd.randint(0, 23))
        env.cr.execute('UPDATE coop_deal SET create_date = %s, funnel_date = %s '
                       'WHERE id = %s AND signed_on IS NULL', (when, when.date(), deal.id))
        stats['made'] += 1
    Deal.invalidate_model(['create_date', 'funnel_date'])
    _logger.info('Обращения по навыкам: %s', stats)
    return stats['made']

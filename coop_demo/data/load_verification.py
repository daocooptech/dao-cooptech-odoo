# -*- coding: utf-8 -*-
"""Ступени верификации в демо-данных — разбросом, а не всем поровну.

Решение владельца: раздать ступени вразнобой, включая тех, кому
публиковать не положено. Если подтвердить всех, на стенде не увидеть ни
одного отказа, и проверить, что человек читает при нехватке ступени,
будет не на чем.

Объявления тех, кто не дотягивает, уходят в черновики. Это не порча
данных, а приведение их в согласие с правилами: опубликованное
объявление от неподтверждённого участника — то самое, чего правила и не
допускают.
"""
import logging

_logger = logging.getLogger(__name__)

# Доли ступеней у людей. Подобраны так, чтобы каталог остался каталогом,
# а отказ всё равно было на чём увидеть: большинство подтверждено, но
# каждый двадцатый не дотягивает даже до публикации.
PEOPLE_MIX = (
    ['identity'] * 16
    + ['contact'] * 2
    + ['account']
    + ['none']
)

# У организаций подтверждение одно — сверка с реестром. Часть заявок ещё
# не рассмотрена: экран «ожидает проверки» должен быть на чём проверить.
ORG_MIX = ['registry'] * 8 + ['pending'] + ['none']

IDENTITY_METHODS = ['inperson', 'inperson', 'esia', 'goskey']


def load_verification(env):
    Verification = env['coop.verification'].sudo()
    Partner = env['res.partner'].sudo()

    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')
    organizations = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)], order='id')

    existing = set(Verification.search([]).mapped(
        lambda v: (v.partner_id.id, v.kind)))
    created = 0

    def add(partner, kind, method, state='confirmed', index=0):
        nonlocal created
        if (partner.id, kind) in existing:
            return
        values = {
            'partner_id': partner.id,
            'kind': kind,
            'method': method,
            'state': state,
        }
        if state == 'confirmed':
            values['confirmed_on'] = '20%02d-%02d-%02d 10:00:00' % (
                22 + (index % 4), 1 + (index % 12), 1 + (index % 27))
        if kind == 'registry':
            # Сверка с реестром устаревает: сведения в ЕГРЮЛ меняются, и
            # выписка годичной давности ничего не подтверждает.
            #
            # Истёкших ровно столько, сколько нужно, чтобы состояние было
            # на чём посмотреть. Раньше срок истекал у половины
            # организаций разом, и вместе с ним из каталога уходили их
            # объявления — каталог пустел не потому, что так задумано, а
            # потому, что дата была подобрана неудачно.
            expired = index % 7 == 3
            values['expires_on'] = '20%02d-%02d-%02d' % (
                25 if expired else 28 + (index % 2),
                1 + (index % 12), 1 + (index % 27))
        Verification.create(values)
        existing.add((partner.id, kind))
        created += 1

    for index, person in enumerate(people):
        level = PEOPLE_MIX[index % len(PEOPLE_MIX)]
        if level == 'none':
            continue
        add(person, 'email', 'self', index=index)
        if level in ('contact', 'identity'):
            add(person, 'phone', 'self', index=index)
        if level == 'identity':
            add(person, 'identity',
                IDENTITY_METHODS[index % len(IDENTITY_METHODS)], index=index)

    for index, organization in enumerate(organizations):
        mode = ORG_MIX[index % len(ORG_MIX)]
        if mode == 'none':
            continue
        add(organization, 'registry', 'registry',
            state='confirmed' if mode == 'registry' else 'pending', index=index)

    _logger.info('Подтверждения: создано %s', created)
    _demote_unpublishable(env)


def _demote_unpublishable(env):
    """Снять с публикации то, что по правилам опубликовать нельзя.

    Ступень «контакт подтверждён» нужна для навыков и ресурсов,
    «личность» — для вакансий. Данные загружались до появления ступеней, и
    без этого прохода в каталоге остались бы объявления, которые сами
    правила размещать не дают, — расхождение, которое потом ищут неделю.
    """
    moved = {}
    for model, owner_field, level, live in (
        ('coop.resource', 'owner_id', 'contact', 'published'),
        ('coop.skill.offer', 'partner_id', 'contact', 'published'),
        ('coop.vacancy', 'partner_id', 'identity', 'published'),
        # Проект собирает чужие деньги и чужой труд, поэтому открыть сбор
        # может только подтверждённый инициатор — как и требует
        # `action_open_gathering`.
        ('coop.project', 'partner_id', 'identity', 'gathering'),
    ):
        records = env[model].sudo().search([('state', '=', live)])
        weak = records.filtered(
            lambda r: not r[owner_field].coop_level_at_least(level))
        if weak:
            weak.write({'state': 'draft'})
        moved[model] = len(weak)
    _logger.info('Снято с публикации по нехватке ступени: %s', moved)

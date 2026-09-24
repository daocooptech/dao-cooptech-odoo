# -*- coding: utf-8 -*-
"""Избранное главного участника витрины (решение 408).

Около ста восьмидесяти отметок во всех каталогах, где есть карточки:
люди, организации, проекты, сообщества, ресурсы, навыки, вакансии,
события, программы, склады, НМА и ЦФА — по-разному, от пяти до
двадцати пяти, чтобы вкладки не были одинаковыми. Даты добавления —
разные, за последние три месяца. У других участников — понемногу, чтобы
сердечки в каталогах стояли не только у одного человека.

Прогон один: если у главного участника отметки уже есть, ничего не
делается.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

PLAN = [
    ('res.partner', [('coop_is_participant', '=', True), ('is_company', '=', False)], 25),
    ('res.partner', [('coop_is_participant', '=', True), ('is_company', '=', True)], 18),
    ('coop.project', [], 20),
    ('coop.community', [], 14),
    ('coop.resource', [], 25),
    ('coop.skill.offer', [], 15),
    ('coop.vacancy', [], 16),
    ('coop.event', [], 12),
    ('coop.program', [], 8),
    ('coop.warehouse.offer', [], 9),
    ('coop.intangible', [], 7),
    ('coop.cfa.issue', [], 6),
]
TEST_NAMES = ('Danil', 'Proverka Vyhoda')


def load_favorites(env, login='dashkevich'):
    Favorite = env['coop.favorite'].sudo()
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1).partner_id
    if not showcase:
        return 0
    if Favorite.search_count([('partner_id', '=', showcase.id)], limit=1):
        _logger.info("Избранное: уже наполнено, пропускаю")
        return 0
    rnd = random.Random(20260924 + 410)
    now = datetime.now()
    people = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('name', 'not in', TEST_NAMES), ('id', '!=', showcase.id)])
    rows = []
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    for model, domain, count in PLAN:
        if model not in env:
            continue
        # Только то, что главный участник действительно видит: закрытое
        # от него в избранном не показалось бы, и числа вкладок разошлись
        # бы с тем, что отмечено (прогон на копии: из 16 вакансий видно 8).
        Model = env[model].with_user(user)
        extra = [('name', 'not in', TEST_NAMES), ('id', '!=', showcase.id)] if model == 'res.partner' else []
        ids = Model.search(domain + extra).ids
        if not ids:
            continue
        for rid in rnd.sample(ids, min(count, len(ids))):
            rows.append((showcase.id, model, rid))
        # Отметки других участников — по одной-две на сотню записей.
        for rid in rnd.sample(ids, min(len(ids) // 8, len(ids))):
            fan = rnd.choice(people)
            rows.append((fan.id, model, rid))
    seen, create = set(), []
    for partner_id, model, rid in rows:
        if (partner_id, model, rid) in seen:
            continue
        seen.add((partner_id, model, rid))
        create.append({'partner_id': partner_id, 'res_model': model, 'res_id': rid})
    records = Favorite.create(create)
    # Даты добавления — разные: избранное копилось, а не появилось разом.
    for record in records:
        when = now - timedelta(days=rnd.randint(0, 90), hours=rnd.randint(0, 23),
                               minutes=rnd.randint(0, 59))
        env.cr.execute("UPDATE coop_favorite SET create_date = %s WHERE id = %s",
                       (when, record.id))
    records.invalidate_recordset(['create_date'])
    mine = sum(1 for r in create if r['partner_id'] == showcase.id)
    _logger.info("Избранное: у витрины %s, всего %s", mine, len(create))
    return len(create)

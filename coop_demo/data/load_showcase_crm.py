# -*- coding: utf-8 -*-
"""Лиды витрины dashkevich — для дашборда «Аналитика → CRM» (задача 494,
кусок 5, выбор владельца 28.11.2026).

Общий загрузчик (`load_crm`) раскладывает 160 лидов по всем организациям —
по одному-три на каждую, и дашборд организации пуст. Здесь у каждой
организации dashkevich — 150 лидов за год: открытые по этапам, выигранные,
проигранные с причиной; источники и причины — по-русски, город — город
клиента, менеджеры — держатели «Сделок» организации.
Повторяемо: ключ лида `crm-sc#<орг>.<n>`.
"""
import logging
import random
from datetime import datetime, timedelta

from . import load_crm as lc
from . import load_sales as ls

_logger = logging.getLogger(__name__)

LEADS = 150
SOURCES = [
    ('Каталог площадки', 30), ('Рекомендация участника', 18), ('Повторный клиент', 14),
    ('Сайт организации', 12), ('Выставка', 8), ('Холодный звонок', 7),
    ('Telegram-канал', 6), ('ВКонтакте', 5),
]
LOST = ['Слишком дорого', 'Выбрали другого поставщика', 'Не устроили сроки',
        'Нет бюджета', 'Пропал контакт', 'Недостаточно запасов']
WORKS = [
    'электромонтаж цеха', 'щитовую 0,4 кВ', 'наружное освещение', 'вентиляцию склада',
    'пусконаладку автоматики', 'энергоаудит', 'учёт электроэнергии', 'молниезащиту',
    'кабельные линии', 'обслуживание подстанции', 'видеонаблюдение', 'слаботочные сети',
]
# Темы — под услугу: «Поставка» и «Оптовая партия» общего загрузчика
# к работам и аренде не подходят («Поставка электромонтаж цеха»).
TOPICS = ['Запрос цены на %s', 'Договор на %s', 'Коммерческое предложение на %s',
          'Повторный заказ на %s', 'Расчёт стоимости: %s']
# ТСН продаёт не работы, а пользование общим имуществом дома.
WORKS_TSN = [
    'аренду нежилого помещения', 'размещение вывески на фасаде', 'аренду машино-места',
    'установку антенны на кровле', 'аренду подвала под склад', 'размещение банкомата',
    'аренду колясочной под мастерскую', 'размещение рекламы в лифтах',
]


def _named(env, model, names):
    Model = env[model].sudo()
    out = {}
    for name in names:
        rec = Model.search([('name', '=', name)], limit=1) or Model.create({'name': name})
        out[name] = rec
    return out


def load_showcase_crm(env, login='dashkevich'):
    if 'crm.lead' not in env:
        return 0
    Lead = env['crm.lead'].sudo().with_context(active_test=False, mail_create_nolog=True,
                                               tracking_disable=True)
    sources = _named(env, 'utm.source', [n for n, _ in SOURCES])
    weights = [w for _, w in SOURCES]
    reasons = list(_named(env, 'crm.lost.reason', LOST).values())
    stages = env['crm.stage'].sudo().search([('is_won', '=', False)], order='sequence')
    won_stage = env['crm.stage'].sudo().search([('is_won', '=', True)], limit=1)
    clients = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True), ('city', '!=', False)], order='id')
    now = datetime.now().replace(microsecond=0)
    made = 0
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    # Все организации dashkevich с компанией учёта — и те, где «Сделки»
    # держит не он (ТСН «Прибрежное», владелец 28.11).
    orgs = ls._showcase(env, login) | env['coop.membership'].sudo().search([
        ('partner_id', '=', user.partner_id.id), ('state', '=', 'active'),
        ('organization_id.coop_company_id', 'in', user.company_ids.ids),
    ]).organization_id
    for org in orgs:
        company = org.coop_company_id
        sellers = env['coop.membership'].sudo().search([
            ('organization_id', '=', org.id), ('state', '=', 'active'),
            ('power_ids.code', '=', 'deal')]).partner_id.user_ids.filtered(
            lambda u: not u.share and company in u.company_ids)
        if not sellers:
            continue
        team = env['crm.team'].sudo().search([('company_id', '=', company.id)], limit=1)
        rnd = random.Random(20261128 + org.id)
        pool = clients.filtered(lambda p: p != org and p not in sellers.partner_id)
        tsn = org.name.startswith(('ТСН', 'ТСЖ'))
        works, top = (WORKS_TSN, 360000) if tsn else (WORKS, 2400000)
        for number in range(LEADS):
            key = 'crm-sc#%s.%s' % (org.id, number)
            if Lead.search_count([('coop_import_key', '=', key)]):
                continue
            client = pool[rnd.randrange(len(pool))]
            seller = sellers[rnd.randrange(len(sellers))]
            created = now - timedelta(days=rnd.randint(0, 360), hours=rnd.randint(0, 9))
            roll = rnd.random()
            # Старые лиды чаще закрыты: свежий ещё в работе.
            age = (now - created).days
            closed = roll < (0.85 if age > 90 else 0.45)
            outcome = ('won' if rnd.random() < 0.42 else 'lost') if closed else 'pending'
            vals = {
                'name': rnd.choice(TOPICS) % rnd.choice(works),
                'type': 'opportunity',
                'partner_id': client.id,
                'city': client.city,
                'user_id': seller.id,
                'team_id': team.id or False,
                'company_id': company.id,
                'source_id': sources[rnd.choices(list(sources), weights)[0]].id,
                'expected_revenue': float(rnd.randrange(top // 60, top, 5000)),
                'priority': rnd.choice(('0', '0', '1', '2', '3')),
                'description': '<p>%s</p>' % rnd.choice(lc.NOTES),
                'coop_import_key': key,
            }
            if outcome == 'won' and won_stage:
                vals['stage_id'] = won_stage.id
            elif stages:
                vals['stage_id'] = stages[rnd.randrange(len(stages))].id
            lead = Lead.with_company(company).create(vals)
            if outcome == 'lost':
                lead.action_set_lost(lost_reason_id=rnd.choice(reasons).id)
            closed_at = created + timedelta(days=rnd.randint(3, 60)) if closed else None
            if closed_at and closed_at > now:
                closed_at = now
            env.cr.execute(
                "UPDATE crm_lead SET create_date = %s, date_open = %s, date_closed = %s,"
                " date_deadline = %s WHERE id = %s",
                (created, created, closed_at,
                 (created + timedelta(days=rnd.randint(14, 75))).date(), lead.id))
            made += 1
    env['crm.lead'].invalidate_model()
    _logger.info('CRM витрины: лидов заведено %s', made)
    return made

# -*- coding: utf-8 -*-
"""Лиды организаций — действиями самих людей (решение 450).

Лид заводит держатель полномочия «Сделки» своей организации, своими
правами и в её компании учёта — как сделал бы живой менеджер: клиент —
другой участник площадки (человек или организация), сумма, стадия, дела
по лиду (звонок, встреча, письмо; часть просрочена), заметка. Дальше по
ходу: часть лидов проиграна с причиной, часть превращена в сделку
площадки кнопкой «Создать сделку» — тоже от имени менеджера.

Повторяемо: ключ лида — организация и номер; уже заведённые пропускаются.
Жребий — от номера организации.
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

TARGET = 160
TOPICS = [
    'Поставка %s', 'Запрос цены на %s', 'Оптовая партия: %s', 'Договор на %s',
    'Пробная закупка: %s', 'Сезонный заказ — %s', 'Повторный заказ: %s',
]
GOODS = [
    'зерно', 'льноволокно', 'пиломатериалы', 'мёд', 'молочную продукцию',
    'ремонт техники', 'доставку грузов', 'монтаж оборудования', 'ткани',
    'семена', 'удобрения', 'бухгалтерские услуги', 'аренду склада',
    'переработку сырья', 'металлоконструкции', 'сувенирную продукцию',
]
NOTES = [
    'Клиент нашёл нас через каталог ресурсов площадки.',
    'Просят образцы и сертификаты до конца месяца.',
    'Готовы на предоплату 30 %, остальное — после приёмки.',
    'Нужна доставка до их склада, уточнить тариф.',
    'Сравнивают с двумя другими поставщиками.',
    'Пришли по рекомендации от соседнего кооператива.',
]
LOST_REASONS = ('crm.lost_reason_1', 'crm.lost_reason_2', 'crm.lost_reason_3')
ACTIVITIES = [
    ('mail.mail_activity_data_call', 'Созвониться, уточнить объём'),
    ('mail.mail_activity_data_meeting', 'Встреча на складе'),
    ('mail.mail_activity_data_email', 'Отправить коммерческое предложение'),
    ('mail.mail_activity_data_todo', 'Подготовить расчёт доставки'),
]


def load_crm(env, target=TARGET):
    if 'crm.lead' not in env or 'coop.vat.regime' not in env:
        return 0
    Lead = env['crm.lead'].sudo()
    have = Lead.search_count([('coop_import_key', '!=', False)])
    if have >= target:
        _logger.info('CRM: лидов уже %s, пропускаю', have)
        return 0
    Users = env['res.users']
    stages = env['crm.stage'].sudo().search([('is_won', '=', False)], order='sequence')
    clients = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True)], order='id')
    orgs = env['res.partner'].sudo().search([
        ('is_company', '=', True), ('coop_is_participant', '=', True),
        ('coop_company_id', '!=', False)], order='id')
    made = deals = 0
    today = date.today()
    for org in orgs:
        if have + made >= target:
            break
        rnd = random.Random(20261010 + org.id)
        sellers = env['coop.membership'].sudo().search([
            ('organization_id', '=', org.id), ('state', '=', 'active'),
            ('power_ids.code', '=', 'deal')]).partner_id.user_ids.filtered(
            lambda u: not u.share and org.coop_company_id in u.company_ids)
        if not sellers:
            continue
        company = org.coop_company_id
        for number in range(rnd.choice((0, 1, 1, 2, 2, 3))):
            key = 'crm#%s.%s' % (org.id, number)
            if Lead.search_count([('coop_import_key', '=', key)]):
                continue
            seller = sellers[rnd.randrange(len(sellers))]
            client = clients[rnd.randrange(len(clients))]
            if client == org or client in seller.partner_id:
                continue
            as_seller = env['crm.lead'].with_user(seller).with_company(company)
            lead = as_seller.create({
                'name': rnd.choice(TOPICS) % rnd.choice(GOODS),
                'type': 'opportunity',
                'partner_id': client.id,
                'user_id': seller.id,
                'expected_revenue': float(rnd.randrange(20000, 1500000, 5000)),
                'priority': rnd.choice(('0', '0', '1', '2', '3')),
                'stage_id': stages[rnd.randrange(len(stages))].id if stages else False,
                'description': '<p>%s</p>' % rnd.choice(NOTES),
                'date_deadline': today + timedelta(days=rnd.randint(-10, 60)),
                'coop_import_key': key,
            })
            made += 1
            # Дело по лиду — у менеджера; треть уже просрочена.
            xmlid, summary = rnd.choice(ACTIVITIES)
            lead.activity_schedule(
                xmlid, date_deadline=today + timedelta(days=rnd.randint(-7, 14)),
                summary=summary, user_id=seller.id)
            roll = rnd.random()
            if roll < 0.15:
                reason = env.ref(rnd.choice(LOST_REASONS), raise_if_not_found=False)
                lead.action_set_lost(lost_reason_id=reason.id if reason else False)
            elif roll < 0.40:
                lead.action_coop_create_deal()
                deals += 1
    _logger.info('CRM: лидов заведено %s, из них в сделки %s', made, deals)
    return made

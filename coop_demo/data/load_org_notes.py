# -*- coding: utf-8 -*-
"""Заметки организаций — общие для действующего состава (решение 655,
задача 428).

Заметку заводит кто-то из состава своими правами, видят её все, кто
сейчас состоит. У организаций, где состоит dashkevich, заметок больше —
восемь-десять, у остальных по одной-три. Разброс: со сроком и без,
выполненные, в архиве; авторы разные. В тексты подставляется название
организации и город, поэтому копий одной строки нет.

Повторяемо: организация, у которой общие заметки уже есть, пропускается.
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

TARGET = 130
NOTES = [
    ('Повестка общего собрания', '<ul><li>Отчёт правления за год</li><li>Утверждение сметы</li><li>Приём новых членов</li></ul>'),
    ('Сверка паевых взносов', '<p>У троих взнос внесён частично — напомнить до конца месяца.</p>'),
    ('Договор аренды склада — {c}', '<p>Срок истекает через два месяца. Запросить у арендодателя новую ставку.</p>'),
    ('Поставщики упаковки', '<ul><li>Плёнка — дешевле у соседнего кооператива</li><li>Коробки — прежний поставщик</li></ul>'),
    ('Кто отвечает за отгрузки', '<p>Пн–ср — Иван, чт–пт — Мария. Ключи от склада — у сторожа.</p>'),
    ('Идеи для {o}', '<p>Совместная закупка с соседями, своя витрина на ярмарке выходного дня в {c}.</p>'),
    ('Налоговый календарь', '<p>Декларация и взносы — до 25-го числа. Ответственный — бухгалтер.</p>'),
    ('Проверка из {c}', '<p>Подготовить устав, протоколы собраний и реестр членов.</p>'),
    ('Ремонт техники', '<p>Трактор — замена сцепления, смета 48 000 ₽. Голосовать на правлении.</p>'),
    ('Контакты в администрации {c}', '<p>Отдел поддержки предпринимательства, приём по вторникам.</p>'),
    ('Новые члены — собеседования', '<p>Две заявки ждут разговора. Назначить встречу на этой неделе.</p>'),
    ('Сайт и страница {o}', '<p>Обновить фото продукции и прайс, проверить телефон в контактах.</p>'),
    ('Отчёт ревизионной комиссии', '<p>Замечаний нет, кроме просроченного акта сверки с перевозчиком.</p>'),
    ('Сезонный план работ', '<ul><li>Март — закупка семян</li><li>Май — посадка</li><li>Сентябрь — уборка</li></ul>'),
]


def load_org_notes(env, login='dashkevich', target=TARGET):
    if 'coop_org_id' not in env['project.task']._fields:
        _logger.warning('Заметки организаций: coop_orgs не обновлён, демо пропущено')
        return 0
    Task = env['project.task'].sudo().with_context(
        mail_create_nolog=True, tracking_disable=True, active_test=False)
    have = Task.search_count([('coop_org_id', '!=', False)])
    if have >= target:
        _logger.info('Заметки организаций: уже %s, пропускаю', have)
        return 0
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    Membership = env['coop.membership'].sudo()
    active = Membership.search([('state', '=', 'active'),
                                ('organization_id.is_company', '=', True)])
    orgs = active.organization_id.sorted('id')
    mine = active.filtered(lambda m: m.partner_id == showcase.partner_id).organization_id
    today = date.today()
    made = 0
    for org in mine + (orgs - mine):
        if have + made >= target:
            break
        if Task.search_count([('coop_org_id', '=', org.id)]):
            continue
        authors = active.filtered(lambda m: m.organization_id == org).partner_id.user_ids.filtered(
            lambda u: not u.share and u.active)
        if not authors:
            continue
        rnd = random.Random(20261115 + org.id)
        count = rnd.randint(8, 10) if org in mine else rnd.choice((0, 1, 1, 2, 3))
        for name, body in rnd.sample(NOTES, k=min(count, len(NOTES))):
            author = showcase if org in mine and showcase in authors and rnd.random() < 0.4 \
                else authors[rnd.randrange(len(authors))]
            city = org.city or 'городе'
            note = Task.with_user(author).create({
                'name': name.format(o=org.name, c=city),
                'description': body.format(o=org.name, c=city),
                'project_id': False,
                'coop_org_id': org.id,
                'user_ids': [(6, 0, [author.id])],
                'date_deadline': today + timedelta(days=rnd.randint(-15, 45)) if rnd.random() < 0.5 else False,
                'priority': '1' if rnd.random() < 0.15 else '0',
            })
            if rnd.random() < 0.2:
                note.state = '1_done'
            if rnd.random() < 0.05:
                note.active = False
            made += 1
    _logger.info('Заметки организаций: добавлено %s', made)
    return made

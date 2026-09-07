# -*- coding: utf-8 -*-
"""Целевые программы кооперации из макета плюс добор по регионам.

Десять программ макета — не выдумка составителя: у каждой стоит работа,
из которой взята механика (Чаянов, Остром, Шольц). Эти десять переносим
как есть, вместе с первоисточниками.

Добор идёт теми же механиками в других городах, и это не подделка под
объём: одна и та же программа — снабженческая, жилищная, кредитная —
действительно заводится в разных местах разными кооперативами. Меняются
организатор, город, фонд и число участников; суть остаётся.
"""
import io
import json
import logging
import os
import random
import re

from odoo import fields

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

INDUSTRY = {
    'Сельское хозяйство': 'agriculture',
    'ИТ и цифровая экономика': 'it',
    'Строительство и жильё': 'housing',
    'Ремесленное производство': 'craft',
    'Логистика и сбыт': 'trade',
    'Образование': 'education',
    'Зелёная энергетика': 'energy',
    'Микрофинансирование': 'trade',
    'Здравоохранение и соцпомощь': 'other',
    'Культура и местные сообщества': 'other',
}

# Механика программы: из чего она складывается на деле. Взято из карточки
# макета — там эти пункты стоят со значками, и они же объясняют участнику,
# во что он ввязывается, ещё до вступления.
STEPS = {
    'agriculture': [
        ('📦', 'Совместная закупка семян и техники'),
        ('🌾', 'Разделение полевых работ по сезону'),
        ('🏬', 'Общий склад хранения урожая'),
        ('🤝', 'Самостоятельность хозяйства сохраняется'),
    ],
    'it': [
        ('📜', 'Юридический шаблон устава цифрового кооператива'),
        ('🧑‍🏫', 'Менторская поддержка команд'),
        ('🖥️', 'Общая инфраструктура в складчину'),
    ],
    'housing': [
        ('🏗️', 'Общий подряд на строительные работы'),
        ('📐', 'Проект и смета на весь дом сразу'),
        ('🔑', 'Распределение долей по паям'),
    ],
    'craft': [
        ('🛠️', 'Мастерская в общем пользовании'),
        ('📦', 'Закупка сырья партией'),
        ('🏷️', 'Общая марка и витрина сбыта'),
    ],
    'trade': [
        ('🚚', 'Общий транспорт и маршруты'),
        ('📦', 'Оптовая закупка на всех'),
        ('🏬', 'Склад в складчину'),
    ],
    'education': [
        ('👩‍🏫', 'Общие преподаватели и программа'),
        ('🏫', 'Помещение в общем пользовании'),
        ('📚', 'Учебные материалы в складчину'),
    ],
    'energy': [
        ('☀️', 'Общая генерация на кооператив'),
        ('🔌', 'Подключение и учёт'),
        ('💡', 'Распределение выработки по паям'),
    ],
    'other': [
        ('🤝', 'Общее дело на нескольких участников'),
        ('📦', 'Складчина на закупки'),
    ],
}

NEEDS = [
    ('Координатор программы на сезон', 'people', 0),
    ('Техника в лизинг', 'equipment', 900000),
    ('Взнос в общий фонд', 'money', 300000),
    ('Материалы на первый этап', 'materials', 450000),
    ('Юрист по кооперативному праву', 'knowledge', 0),
    ('Помещение под общий склад', 'equipment', 0),
]

TARGET = 110


def _money(text):
    """«4 200 000 ₽» → 4200000.0."""
    digits = re.sub(r'[^\d]', '', text or '')
    return float(digits) if digits else 0.0


def _months(text):
    match = re.search(r'(\d+)', text or '')
    return int(match.group(1)) if match else 12


def _source(text):
    """Разобрать строку первоисточника на автора, работу, годы и суть.

    Ссылки в макете записаны по-разному: у одних название в кавычках, у
    других — оборот «исследования EMES о WISE», у третьих суть после
    тире отсутствует вовсе. Разбор идёт по частям, а не одним шаблоном:
    иначе четыре ссылки из десяти теряют автора и год, и в карточке
    остаётся «без основы» там, где основа есть.
    """
    if not text:
        return {}
    text = text.strip()
    result = {}

    # Годы — в скобках, они же отделяют «шапку» от сути.
    years = re.search(r'\(([^)]*\d{4}[^)]*)\)', text)
    if years:
        result['source_year'] = years.group(1).strip()
        head = text[:years.start()].strip().rstrip(',')
        tail = text[years.end():].strip()
    else:
        head, tail = text, ''

    # Суть — после тире, если оно есть.
    tail = re.sub(r'^[\s—–-]+', '', tail).strip()
    if tail:
        result['source_summary'] = tail

    # Название работы — в кавычках; без них вся шапка идёт автором, а
    # уточнение вида «исследования EMES о WISE» становится названием.
    quoted = re.search(r'[«"](.+?)[»"]', head)
    if quoted:
        result['source_title'] = quoted.group(1).strip()
        author = head[:quoted.start()].strip().rstrip(',')
    else:
        parts = re.split(r',\s*(?=[а-яa-z])', head, maxsplit=1)
        author = parts[0].strip()
        if len(parts) > 1:
            result['source_title'] = parts[1].strip()
    if author:
        result['source_author'] = author
    if not result.get('source_summary'):
        result['source_summary'] = text
    return result


def load_programs(env, target=TARGET):
    Program = env['coop.program'].sudo()
    Step = env['coop.program.step'].sudo()
    Need = env['coop.program.need'].sudo()
    Partner = env['res.partner'].sudo()

    if Program.search_count([]) >= target // 2:
        _logger.info('Целевые программы: уже наполнены, пропускаю')
        return

    with io.open(os.path.join(HERE, 'programs.json'), encoding='utf-8') as fh:
        rows = json.load(fh)

    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)],
        order='id')
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not companies:
        _logger.warning('Нет кооперативов — программы не наполняю')
        return

    cities = sorted({p.city for p in companies if p.city}) or ['Москва']
    # Участник показа набирается отдельно, шестью программами: попав в
    # общую выборку, он оказывался в половине из ста десяти, и «мои
    # программы» переставали что-либо означать.
    showcase = env['res.users'].sudo().search([('login', '=', 'dashkevich')], limit=1)
    pool = [pid for pid in people.ids if pid != showcase.partner_id.id]
    rnd = random.Random(20260907)
    created = 0

    for index in range(target):
        row = rows[index % len(rows)]
        wave = index // len(rows)
        industry = INDUSTRY.get(row['industry'], 'other')
        organizer = companies[index % len(companies)]
        city = row['city'] if wave == 0 else cities[index % len(cities)]
        name = row['name'] if wave == 0 else '%s — %s' % (row['name'], city)

        # Состояние зависит от возраста: свежие набирают участников,
        # давние идут или завершились. Иначе на первом экране все
        # программы одинаково «идут», и фильтр по состоянию бесполезен.
        age = rnd.random()
        state = ('collecting' if age < 0.3 else
                 'active' if age < 0.8 else 'finished')

        values = {
            'name': name,
            'organizer_id': organizer.id,
            'city': city,
            'industry': industry,
            'fund_amount': _money(row['fund']) * rnd.uniform(0.7, 1.4),
            'duration_months': _months(row['duration']),
            'description': '<p>%s</p>' % row['text'],
            'state': state,
        }
        values.update(_source(row['source']))
        program = Program.create(values)

        for order, (icon, step_name) in enumerate(STEPS.get(industry, STEPS['other'])):
            Step.create({
                'program_id': program.id,
                'sequence': (order + 1) * 10,
                'icon': icon,
                'name': step_name,
            })

        for order, (need_name, kind, amount) in enumerate(
                rnd.sample(NEEDS, rnd.randint(2, 4))):
            Need.create({
                'program_id': program.id,
                'sequence': (order + 1) * 10,
                'name': need_name,
                'kind': kind,
                'amount': amount * rnd.uniform(0.6, 1.5) if amount else 0.0,
                'state': 'covered' if rnd.random() < 0.35 else 'open',
            })

        # Участники: столько, сколько заявлено в макете, с разбросом.
        wanted = int(re.sub(r'[^\d]', '', row['people']) or 20)
        wanted = max(3, min(int(wanted * rnd.uniform(0.5, 1.2)), len(pool)))
        program.participant_ids = [(6, 0, rnd.sample(pool, wanted))]
        program.subscriber_ids = [(6, 0, rnd.sample(
            pool, min(rnd.randint(2, 20), len(pool))))]
        created += 1

    _spread_created(env, rnd)
    _showcase(env, rnd)
    _logger.info('Целевые программы: создано %s', created)


def _spread_created(env, rnd):
    """Развести даты создания: каталог сортирован по ним."""
    for record_id in env['coop.program'].sudo().search([]).ids:
        env.cr.execute(
            "UPDATE coop_program SET create_date = now() - (%s || ' days')::interval "
            "WHERE id = %s", (rnd.randint(0, 500), record_id))
    env.invalidate_all()


def _showcase(env, rnd, login='dashkevich'):
    """Участник показа состоит в нескольких программах.

    Вкладка «мои программы» без единой записи выглядит поломкой, а не
    пустотой: человек решает, что раздел не работает, и не проверяет
    дальше.
    """
    user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if not user:
        return
    me = user.partner_id
    programs = env['coop.program'].sudo().search([])
    mine = programs.filtered(lambda p: me in p.participant_ids)
    if len(mine) >= 4:
        return
    for program in rnd.sample(list(programs - mine), min(6, len(programs))):
        program.participant_ids = [(4, me.id)]
    _logger.info('Витрина программ: участник добавлен в %s программ', 6)

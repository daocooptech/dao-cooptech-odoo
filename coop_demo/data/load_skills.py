# -*- coding: utf-8 -*-
"""Наполнение каталога навыков из макета.

Сто предложений навыка из `skills.html`: чем человек занимается, за
сколько, с каким опытом и какими умениями.

Владельцы берутся по имени из макета — там они указаны у всех ста
карточек. Тех, кого в каталоге людей нет, заводить не нужно: имена в
макете взяты из того же списка участников, и расхождение означало бы
ошибку разбора, а не нового человека.
"""
import base64
import json
import logging
import os

from . import emblems

_logger = logging.getLogger(__name__)

def _state_for(index):
    """Состояние предложения с разбросом.

    В наборе все записи были опубликованными, и проверить на нём
    приостановленное предложение или черновик было физически не на чем —
    а именно в этих состояниях экран и ломается. Доли небольшие: каталог
    должен оставаться каталогом, а не витриной состояний.
    """
    if index % 17 == 5:
        return 'paused'
    if index % 23 == 7:
        return 'draft'
    return 'published'


HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'skills')


def load_skills(env):
    with open(os.path.join(HERE, 'skills.json'), encoding='utf-8') as fh:
        rows = json.load(fh)

    Offer = env['coop.skill.offer'].sudo()
    Partner = env['res.partner'].sudo()
    Skill = env['hr.skill'].sudo()
    skill_type = env.ref('coop_demo.skill_type_craft')

    specializations = {s.name: s for s in env['coop.specialization'].sudo().search([])}
    skills = {s.name: s for s in Skill.search([])}
    people = Partner.search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')

    created = updated = missing_owner = 0

    # Фотография и описание по специализации — из макета. Достроенным
    # предложениям брать их неоткуда, а карточка без снимка и без текста
    # в каталоге выглядит как незаполненная форма, а не как предложение
    # мастера.
    photo_by_spec, texts_by_spec = {}, {}
    photo_by_area, texts_by_area = {}, {}
    for row in rows:
        spec = row['specialization']
        area = row['category']
        if row['photo']:
            name = os.path.basename(row['photo'])
            photo_by_spec.setdefault(spec, name)
            photo_by_area.setdefault(area, name)
        if row['description']:
            texts_by_spec.setdefault(spec, [])
            if row['description'] not in texts_by_spec[spec]:
                texts_by_spec[spec].append(row['description'])
            texts_by_area.setdefault(area, [])
            if row['description'] not in texts_by_area[area]:
                texts_by_area[area].append(row['description'])

    for index, row in enumerate(rows):
        owner = Partner.search(
            [('name', '=', row['owner']), ('is_company', '=', False)], limit=1)
        if not owner:
            # Владельца из макета нет в каталоге — берём по кругу, но
            # считаем: если таких много, значит разбор макета сломан.
            missing_owner += 1
            owner = people[index % len(people)] if people else None
        if not owner:
            continue

        # Умения из чипов карточки. Заводятся в том же типе, что и умения
        # людей: справочник один, и разводить его на «умения человека» и
        # «умения из предложения» значит немедленно получить два списка с
        # одинаковыми названиями.
        skill_ids = []
        for name in row['skills']:
            skill = skills.get(name)
            if not skill:
                skill = Skill.create({'name': name, 'skill_type_id': skill_type.id})
                skills[name] = skill
            skill_ids.append(skill.id)

        specialization = specializations.get(row['specialization'])
        values = {
            'name': row['name'],
            'description': '<p>%s</p>' % row['description'] if row['description'] else False,
            'partner_id': owner.id,
            'coop_specialization_id': specialization.id if specialization else False,
            'skill_ids': [(6, 0, skill_ids)],
            'city': row['city'],
            'ready_to_travel': row['travel'],
            'experience_months': row['experience_months'],
            'rate': row['rate'],
            'rate_kind': row['rate_kind'],
            'rate_period': row['rate_period'],
            'state': _state_for(index),
        }

        photo = os.path.join(PHOTO_DIR, os.path.basename(row['photo'])) if row['photo'] else ''
        if photo and os.path.exists(photo):
            with open(photo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())

        # Опознаём по ключу источника, а не по названию: название
        # правится, и тогда загрузчик заводит запись заново вместо того,
        # чтобы поправить существующую.
        key = 'skills.json#%s' % index
        values['import_key'] = key
        existing = Offer.search([('import_key', '=', key)], limit=1)
        if existing:
            existing.write(values)
            updated += 1
        else:
            Offer.create(values)
            created += 1

    # Предложения остальным участникам. В макете сто карточек держат
    # семнадцать человек, а участников в каталоге сотня: такой перекос
    # читается как сбой данных, а не как живой каталог. Достраиваем по
    # собственной специализации и умениям человека — то есть по тому, что
    # он и так о себе заявил.
    generated = _generate_missing(env, Offer, Partner,
                                  photo_by_spec, texts_by_spec,
                                  photo_by_area, texts_by_area)

    if missing_owner:
        _logger.warning('Каталог навыков: у %s предложений владелец из макета '
                        'не найден среди участников', missing_owner)
    _logger.info('Каталог навыков: из макета %s (создано %s, обновлено %s), '
                 'достроено по участникам %s',
                 len(rows), created, updated, generated)


# Ставка подбирается по специализации: сварщик и бухгалтер стоят
# по-разному, и одинаковая ставка у всех сделала бы фильтр по цене
# бессмысленным. Числа — порядок величины по рынку, не прайс-лист.
RATE_BY_AREA = {
    'Информационные технологии': 150000,
    'Финансы, бухгалтерия': 90000,
    'Юристы': 100000,
    'Строительство, недвижимость': 95000,
    'Медицина, фармацевтика': 75000,
    'Транспорт, логистика, перевозки': 80000,
    'Рабочий персонал': 70000,
    'Производство, сервисное обслуживание': 72000,
    'Сельское хозяйство': 60000,
    'Розничная торговля': 55000,
    'Домашний, обслуживающий персонал': 50000,
}
DEFAULT_RATE = 65000


def _generate_missing(env, Offer, Partner, photo_by_spec, texts_by_spec,
                      photo_by_area, texts_by_area):
    """Завести предложение каждому участнику, у которого его нет.

    Заголовок — название его специализации: человек, назвавшийся
    сварщиком, предлагает сварку. Умения берутся его собственные, ставка —
    по сфере деятельности с разбросом, опыт — из возраста, но не больше
    правдоподобного: сорокалетний электрик мог работать двадцать лет,
    двадцатилетний — нет.
    """
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('coop_specialization_id', '!=', False),
    ])
    with_offer = set(Offer.search([]).mapped('partner_id').ids)

    created = 0
    for index, person in enumerate(people):
        if person.id in with_offer:
            continue

        specialization = person.coop_specialization_id
        area = specialization.category_id.name if specialization.category_id else ''
        base = RATE_BY_AREA.get(area, DEFAULT_RATE)
        # Разброс ±20% по номеру записи: одинаковые ставки в списке
        # выглядят как подставленное значение по умолчанию, каким они и
        # были бы.
        rate = int(base * (0.8 + (index % 9) * 0.05) / 1000) * 1000

        # Опыт: не больше числа лет с восемнадцати. Иначе в каталоге
        # появляется двадцатилетний мастер с пятнадцатью годами стажа.
        possible = max(0, (person.coop_age or 30) - 18)
        years = min(possible, 1 + (index % 12))
        months = (index * 7) % 12

        # Заголовок — первое занятие из перечня специализации.
        # «Электромонтажник, электромонтер, техник-электрик» целиком в
        # заголовке карточки не читается: это строка справочника, а не
        # то, как человек себя называет.
        title = specialization.name.split(',')[0].strip()

        # Описание: своё по специализации, иначе — соседнее по сфере
        # деятельности, иначе — собрано из умений человека. Пустое
        # описание в каталоге хуже общего: по нему не понять, берётся
        # человек за работу или просто числится.
        texts = (texts_by_spec.get(specialization.name)
                 or texts_by_area.get(area) or [])
        if texts:
            description = texts[index % len(texts)]
        elif person.coop_skill_ids:
            description = '%s. Работаю по направлению «%s».' % (
                ', '.join(person.coop_skill_ids.mapped('name')),
                specialization.name)
        else:
            description = 'Работаю по направлению «%s».' % specialization.name

        values = {
            'import_key': 'generated#%s' % person.id,
            'name': title,
            'description': '<p>%s</p>' % description if description else False,
            'partner_id': person.id,
            'coop_specialization_id': specialization.id,
            'skill_ids': [(6, 0, person.coop_skill_ids.ids)],
            'city': person.city or '',
            'ready_to_travel': index % 7 == 0,
            'experience_months': years * 12 + months,
            'rate': rate,
            'rate_kind': 'from' if index % 5 else 'piece',
            'rate_period': 'month',
            'state': 'published',
        }

        photo_name = (photo_by_spec.get(specialization.name)
                      or photo_by_area.get(area))
        photo = os.path.join(PHOTO_DIR, photo_name) if photo_name else ''
        if photo and os.path.exists(photo):
            with open(photo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())
        else:
            # Снимка нет ни у специализации, ни у сферы — ставим знак по
            # роду занятий. Пустое место в строке каталога читается как
            # незагрузившаяся картинка, а знак — как оформление.
            values['image_1920'] = emblems.emblem(
                specialization.name, specialization.name)

        Offer.create(values)
        created += 1

    return created

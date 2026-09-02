# -*- coding: utf-8 -*-
"""Наполнение каталога вакансий из макета.

Сто вакансий из `vacancies.html`: кто нужен, за что, на каких условиях.

Про долю в проекте. В макете она записана процентом — «доля в проекте
5–8%», — но по решению владельца от 2026-09-01 доля не вписывается, а
складывается: вклад участника делится на сумму всех вкладов проекта.
Поэтому процент из макета используется не как значение, а наоборот: из
него и суммы вкладов проекта восстанавливается денежная оценка вклада,
которая и попадает в базу. Дальше процент считается сам и меняется, когда
в проект вносят что-то ещё, — как и должно быть.
"""
import base64
import json
import logging
import os

from . import emblems

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'vacancies')

EMPLOYMENT = {
    'Полная занятость': 'full',
    'Частичная занятость': 'part',
    'Проектная работа': 'project',
    'Волонтёрство': 'volunteer',
}

EXPERIENCE = {
    'Нет опыта': 'none',
    'От 1 года': 'junior',
    'От 3 лет': 'senior',
}

REWARD = {
    'Деньги': 'money',
    'Доля в проекте': 'share',
    'Обмен услугами': 'barter',
    'Волонтёрство': 'volunteer',
}

# Демонстрационные проекты: вакансии от проектов в макете принадлежат
# этим трём. Сумма вкладов нужна, чтобы доля считалась от чего-то —
# иначе процент неизвестен, и показывать вместо него ноль было бы
# неправдой.
DEMO_PROJECTS = [
    ('Строительный 3D-принтер', 12000000),
    ('Круглогодичная теплица', 8500000),
    ('Кооперативный склад', 5000000),
]


def _ensure_projects(env):
    Project = env['project.project'].sudo()
    projects = []
    for name, total in DEMO_PROJECTS:
        project = Project.search([('name', '=', name)], limit=1)
        if not project:
            project = Project.create({'name': name})
        if not project.coop_contribution_total:
            project.coop_contribution_total = total
        projects.append(project)
    return projects



# Добор сверх макета — по тому же основанию, что и в остальных каталогах:
# опубликованных должно быть больше ста, а часть уйдёт в черновики по
# нехватке верификации у того, кто размещает.
EXTRA_TITLES = [
    'Тракторист-машинист', 'Оператор сушильного комплекса', 'Пчеловод',
    'Плотник', 'Сварщик', 'Кровельщик', 'Электромонтажник',
    'Оператор пилорамы', 'Ветеринарный фельдшер', 'Агроном',
    'Кладовщик', 'Водитель категории C', 'Слесарь-ремонтник',
    'Пекарь', 'Сыровар', 'Швея', 'Печник', 'Садовод-питомниковод',
    'Мастер по ремонту техники', 'Бухгалтер на первичку',
]


def _extra_rows(rows, extra):
    cities = sorted({row['city'] for row in rows if row.get('city')})
    extras = []
    for i in range(extra):
        source = rows[(i * 9) % len(rows)]
        city = cities[(i * 7) % len(cities)] if cities else ''
        row = dict(source)
        row['name'] = '%s — %s' % (EXTRA_TITLES[i % len(EXTRA_TITLES)], city)
        row['city'] = city
        extras.append(row)
    return extras

def load_vacancies(env, extra=45):
    with open(os.path.join(HERE, 'vacancies.json'), encoding='utf-8') as fh:
        rows = json.load(fh)
    rows = rows + _extra_rows(rows, extra)

    Vacancy = env['coop.vacancy'].sudo()
    Partner = env['res.partner'].sudo()
    Skill = env['hr.skill'].sudo()
    skill_type = env.ref('coop_demo.skill_type_craft')

    specializations = {s.name: s for s in env['coop.specialization'].sudo().search([])}
    skills = {s.name: s for s in Skill.search([])}
    projects = _ensure_projects(env)

    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')
    companies = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', True)], order='id')

    created = updated = 0

    for index, row in enumerate(rows):
        # Кто ищет. Организацию и человека находим по имени из макета;
        # вакансии от проекта закрепляем за инициатором — организацией, а
        # сам проект ставим отдельным полем.
        owner = Partner.search([('name', '=', row['owner'])], limit=1)
        project = None
        if row['owner_type'] == 'Проект':
            project = projects[index % len(projects)]
            if not owner:
                owner = companies[index % len(companies)] if companies else None
        if not owner:
            pool = people if row['owner_type'] == 'Частное лицо' else companies
            owner = pool[index % len(pool)] if pool else None
        if not owner:
            continue

        # Раньше здесь молча проставлялась верификация владельцу, чтобы
        # каталог опубликовался. Так делать нельзя: подгонять данные под
        # правило значит никогда не увидеть, как правило работает.
        # Ступени раздаёт `load_verification`, и вакансии тех, кто не
        # дотягивает, остаются черновиками — как и должно быть.

        skill_ids = []
        for name in row['skills']:
            skill = skills.get(name)
            if not skill:
                skill = Skill.create({'name': name, 'skill_type_id': skill_type.id})
                skills[name] = skill
            skill_ids.append(skill.id)

        specialization = specializations.get(row['specialization'])
        reward_kind = REWARD.get(row['reward_kind'], 'money')

        values = {
            'name': row['name'],
            'description': '<p>%s</p>' % row['description'] if row['description'] else False,
            'partner_id': owner.id,
            'project_id': project.id if project else False,
            'coop_specialization_id': specialization.id if specialization else False,
            'skill_ids': [(6, 0, skill_ids)],
            'city': row['city'],
            'employment': EMPLOYMENT.get(row['employment'], 'full'),
            'experience_level': EXPERIENCE.get(row['experience'], 'junior'),
            'reward_kind': reward_kind,
            'pay_from': row['pay_from'],
            'pay_to': row['pay_to'],
            'pay_period': row['pay_period'],
            'reward_note': row['reward_note'],
            'state': _state_for(index),
            'import_key': 'vacancies.json#%s' % index,
        }

        if reward_kind == 'share':
            # Процент из макета — это результат, а не ввод: восстанавливаем
            # из него денежную оценку вклада, и дальше процент считается
            # сам. Если процента нет, берём десятую часть суммы вкладов —
            # порядок величины, а не выдуманная точность.
            total = (project or projects[0]).coop_contribution_total
            share = row['share_hint'] or 10
            values['contribution_value'] = round(total * share / 100.0)
            if not values['project_id']:
                values['project_id'] = (project or projects[0]).id

        photo = os.path.join(PHOTO_DIR, os.path.basename(row['photo'])) if row['photo'] else ''
        if photo and os.path.exists(photo):
            with open(photo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())
        else:
            # Снимка нет — ставим знак по роду занятий. Пустое место в
            # плитке читается как незагрузившаяся картинка, а знак — как
            # оформление.
            activity = row['specialization'] or row['name']
            values['image_1920'] = emblems.emblem(row['name'], activity)

        existing = Vacancy.search([('import_key', '=', values['import_key'])], limit=1)
        if existing:
            existing.write(values)
            updated += 1
        else:
            Vacancy.create(values)
            created += 1

    _logger.info('Каталог вакансий: %s записей, создано %s, обновлено %s',
                 len(rows), created, updated)


def _state_for(index):
    """Состояние вакансии с разбросом.

    Закрытые и черновики нужны, чтобы экраны в этих состояниях можно было
    проверить. Доли небольшие: каталог должен оставаться каталогом.
    """
    if index % 19 == 4:
        return 'closed'
    if index % 27 == 9:
        return 'draft'
    return 'published'

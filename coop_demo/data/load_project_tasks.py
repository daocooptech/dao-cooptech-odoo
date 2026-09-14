# -*- coding: utf-8 -*-
"""Задачи и этапы у проектов, доросших до управления.

Связь сбора вкладов с управлением ожила, но проекты в управлении стояли
пустыми: карточка есть, а внутри ни задачи, ни исполнителя, ни срока.
Раздел, который открываешь и видишь пустоту, ничем не лучше отсутствующего
раздела.

Задачи берутся не из воздуха. Их состав повторяет то, как устроена
любая кооперативная затея: сначала договориться и посчитать, потом
закупить и построить, потом запустить и научить людей пользоваться.
Поэтому набор один на всех, а различаются подробности — что именно
закупают и чему учат — по названию проекта.

Исполнители — вкладчики того же сбора, а не случайные участники: работу
в кооперативном проекте делают те, кто в него вложился. Если вкладчиков
не осталось, задача остаётся без исполнителя — это честнее, чем
приписать её первому попавшемуся.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Этапы общие для всех проектов платформы: свои этапы у каждого проекта
# превратили бы сводку по узлу в кашу из сорока названий одного и того же.
STAGES = [
    ('Идея', 10),
    ('В работе', 20),
    ('На проверке', 30),
    ('Готово', 40),
]

# Ход работ: что делают в кооперативном проекте от начала до запуска.
# Первый элемент — название, второй — сколько дней на это обычно уходит,
# третий — доля пути, на которой этап считается пройденным.
BACKBONE = [
    ('Согласовать смету и порядок распределения', 5, 0.10),
    ('Выбрать поставщика и договориться о цене', 7, 0.20),
    ('Закупить материалы и оборудование', 14, 0.35),
    ('Подготовить помещение и подвести коммуникации', 21, 0.50),
    ('Собрать и наладить', 18, 0.65),
    ('Провести приёмку с вкладчиками', 4, 0.75),
    ('Обучить тех, кто будет работать', 6, 0.85),
    ('Запустить и снять первые показатели', 10, 0.95),
]

# Подробности по слову в названии проекта. Ключ ищется в названии, и по
# нему добавляются две задачи, которых в общем ходе работ нет.
DETAILS = {
    'теплиц': [('Составить севооборот на сезон', 6),
               ('Настроить полив и досветку', 9)],
    'принтер': [('Отпечатать пробную стену и замерить прочность', 12),
                ('Написать инструкцию для операторов', 5)],
    'пекарн': [('Согласовать рецептуры и выход теста', 7),
               ('Получить заключение на помещение', 15)],
    'коворкинг': [('Расставить рабочие места и проверить сеть', 6),
                  ('Договориться о правилах пользования', 4)],
    'электростанц': [('Согласовать подключение к сети', 25),
                     ('Замерить выработку за первый месяц', 30)],
    'площадк': [('Проверить покрытие на безопасность', 8),
                ('Договориться о графике уборки', 3)],
    'мастерск': [('Разметить рабочие зоны и хранение', 7),
                 ('Составить график доступа к станкам', 5)],
    'склад': [('Разметить зоны хранения', 6),
              ('Завести учёт приёмки и отгрузки', 8)],
    'сыр': [('Отладить температурный режим камеры', 10),
            ('Провести пробную варку', 6)],
    'пасек': [('Осмотреть семьи и подготовить ульи', 9),
              ('Составить план кочёвки', 5)],
}

TAGS = ['закупка', 'стройка', 'наладка', 'приёмка', 'обучение', 'запуск',
        'документы', 'согласование']


def load_project_tasks(env, per_project=None):
    Project = env['project.project'].sudo()
    Task = env['project.task'].sudo()
    Stage = env['project.task.type'].sudo()
    Collect = env['coop.project'].sudo()

    collects = Collect.search([('project_id', '!=', False)], order='id')
    if not collects:
        _logger.warning('Проектов в управлении нет — задачи не завожу')
        return 0

    projects = collects.mapped('project_id')
    # Раскладка по этапам идёт до проверки на «уже заведены»: задачи
    # заводятся один раз, а этап меняется вслед за состоянием проекта, и
    # пропускать его вместе с задачами нельзя.
    _spread_project_stages(env)
    if Task.search_count([('project_id', 'in', projects.ids)]) >= len(projects):
        _logger.info('Задачи проектов: уже заведены, пропускаю')
        return 0

    stages = _ensure_stages(Stage, projects)
    tags = _ensure_tags(env)
    rnd = random.Random(20260914)
    today = fields.Date.today()
    made = 0

    for collect in collects:
        project = collect.project_id
        # Насколько проект продвинулся: у завершённого сделано всё, у
        # запущенного — часть. Именно отсюда берётся распределение задач
        # по этапам, а не из случайного выбора: иначе у завершённого
        # проекта половина работ висела бы в идее.
        progress = 1.0 if collect.state == 'done' else rnd.uniform(0.3, 0.8)
        # Своей даты запуска у сбора нет, поэтому отсчитываем от даты
        # первого принятого вклада: раньше него работы начаться не могли.
        accepted = collect.contribution_ids.filtered(
            lambda c: c.state == 'accepted' and c.accepted_on)
        started = (min(accepted.mapped('accepted_on')) if accepted
                   else today - timedelta(days=rnd.randint(30, 300)))

        rows = list(BACKBONE)
        for token, extra in DETAILS.items():
            if token in (collect.name or '').lower():
                for index, (title, days) in enumerate(extra):
                    rows.insert(3 + index, (title, days, 0.45 + index * 0.1))
                break

        performers = collect.contribution_ids.filtered(
            lambda c: c.state == 'accepted').mapped('partner_id')
        users = env['res.users'].sudo().search(
            [('partner_id', 'in', performers.ids)]) if performers else None

        offset = 0
        for order, (title, days, milestone) in enumerate(rows):
            done = progress >= milestone
            checking = not done and progress >= milestone - 0.12
            if done:
                stage = stages['Готово']
            elif checking:
                stage = stages['На проверке']
            elif progress >= milestone - 0.3:
                stage = stages['В работе']
            else:
                stage = stages['Идея']

            deadline = started + timedelta(days=offset + days)
            offset += days

            values = {
                'name': title,
                'project_id': project.id,
                'stage_id': stage,
                'sequence': (order + 1) * 10,
                'date_deadline': deadline,
                'tag_ids': [(6, 0, [tags[TAGS[order % len(TAGS)]]])],
                'description': '<p>Шаг %s из %s по проекту «%s».</p>' % (
                    order + 1, len(rows), collect.name),
            }
            if users:
                values['user_ids'] = [(6, 0, [users[order % len(users)].id])]
            with env.cr.savepoint():
                Task.create(values)
                made += 1

    _logger.info('Задач по проектам заведено: %s на %s проектов',
                 made, len(collects))
    return made


def _spread_project_stages(env):
    """Разложить управляемые проекты по этапам ведения.

    Все сто стояли в «Подготовке» — так их перевёл переход на
    кооперативные этапы. Канбан из одного столбца не показывает ни
    перетаскивания, ни свёрнутых этапов, ни того, ради чего этапы вообще
    заведены.

    Этап выводится из того, что с проектом на самом деле: остановленный —
    в «Остановлен», завершённый — в «Итоги», идущий — по готовности.
    Раскладывать наугад значило бы получить проект в «Приёмке» при
    двадцати процентах сбора.
    """
    Collect = env['coop.project'].sudo()
    by_key = {}
    for key in ('preparation', 'supply', 'work', 'acceptance',
                'settlement', 'stopped'):
        stage = env.ref('coop_projects.project_stage_%s' % key,
                        raise_if_not_found=False)
        if stage:
            by_key[key] = stage.id
    if len(by_key) < 6:
        return 0

    moved = 0
    for collect in Collect.search([('project_id', '!=', False)]):
        if collect.state in ('cancelled', 'failed', 'frozen'):
            key = 'stopped'
        elif collect.state == 'done':
            key = 'settlement'
        elif collect.readiness >= 100:
            key = 'acceptance'
        elif collect.readiness >= 70:
            key = 'work'
        elif collect.readiness >= 40:
            key = 'supply'
        else:
            key = 'preparation'
        if collect.project_id.stage_id.id != by_key[key]:
            collect.project_id.sudo().stage_id = by_key[key]
            moved += 1
    if moved:
        _logger.info('Этапы ведения разложены: проектов %s', moved)
    return moved


def _ensure_stages(Stage, projects):
    """Этапы заводятся один раз и привязываются ко всем проектам сразу."""
    found = {}
    for name, sequence in STAGES:
        stage = Stage.search([('name', '=', name)], limit=1)
        if not stage:
            stage = Stage.create({'name': name, 'sequence': sequence})
        # Этап виден в проекте, только если проект указан в его списке.
        stage.write({'project_ids': [(4, project.id) for project in projects]})
        found[name] = stage.id
    return found


def _ensure_tags(env):
    Tag = env['project.tags'].sudo()
    found = {}
    for name in TAGS:
        tag = Tag.search([('name', '=', name)], limit=1)
        if not tag:
            tag = Tag.create({'name': name})
        found[name] = tag.id
    return found

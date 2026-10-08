# -*- coding: utf-8 -*-
"""Управление проектами как в работающей организации (решение 452, этап 3).

Разбор ux 08.10.2026: все задачи «в работе», хотя треть стоит в «Готово»;
сроки 2023–2025 при отчётах о ходе в 2026; ни подзадач, ни зависимостей,
ни плановых часов, ни вложений; проекты только из сборов — 55 при норме
100–200, без пустых, остановленных и заведённых вручную.

Здесь три прохода:

1. Задачи проектов сборов: «Готово» закрыто, сроки сдвинуты в 2026 год
   вокруг сегодняшнего дня (часть просрочена), часть отменена, часть
   ждёт предыдущую, у шагов — плановые часы, подзадачи и вложения.
2. Заглушки без владельца — в архив; демо-«Теплица» — в настоящий проект
   кооператива.
3. Проекты без сбора: их ведут организации (своё строительство, ремонт,
   внедрение учёта) и люди (ремонт, мероприятие, курс) — во всех
   состояниях, от пустого замысла до остановленного.

Каждый проход безвреден при повторе: задачи сборов помечаются плановыми
часами, проекты без сбора ищутся по названию.
"""
import base64
import logging
import random
from datetime import datetime, time, timedelta

from odoo import fields

from . import load_project_tasks

_logger = logging.getLogger(__name__)

CITIES = ['Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань',
          'Нижний Новгород', 'Самара', 'Тюмень', 'Пермь', 'Красноярск', 'Омск',
          'Уфа', 'Воронеж', 'Краснодар', 'Ярославль', 'Вологда', 'Хабаровск',
          'Владивосток', 'Калининград', 'Тобольск', 'Ишим', 'Архангельск',
          'Челябинск', 'Ростов-на-Дону', 'Иркутск', 'Псков', 'Тула', 'Курск']

# Подзадачи шагов общего хода работ — по началу названия шага.
SUBTASKS = {
    'Согласовать смету': ['Собрать цены по трём поставщикам',
                          'Разослать смету вкладчикам',
                          'Утвердить смету на собрании'],
    'Выбрать поставщика': ['Запросить коммерческие предложения',
                           'Сравнить сроки и условия оплаты',
                           'Подписать договор поставки'],
    'Закупить материалы': ['Оплатить счёт поставщика',
                           'Согласовать доставку',
                           'Принять поставку и сверить накладную',
                           'Оформить возврат брака'],
    'Подготовить помещение': ['Вызвать электрика на ввод',
                              'Провести воду и канализацию',
                              'Сдать помещение пожарному надзору'],
    'Собрать и наладить': ['Собрать по схеме производителя',
                           'Пробный пуск без нагрузки',
                           'Устранить замечания наладчика'],
    'Провести приёмку': ['Разослать приглашение вкладчикам',
                         'Подписать акт приёмки'],
    'Обучить тех': ['Составить программу на два дня',
                    'Провести занятие и зачёт'],
}

# Вложения к шагам: имя файла и содержимое — по началу названия шага.
ATTACH = {
    'Согласовать смету': ('Смета.csv', 'smeta'),
    'Выбрать поставщика': ('Сравнение предложений.csv', 'offers'),
    'Провести приёмку': ('Акт приёмки.txt', 'act'),
    'Закупить материалы': ('Накладная.txt', 'waybill'),
}

# Проекты без сбора: шаблон — (название, кто ведёт, шаги). Шаг —
# (название, дней, подзадачи). Кто ведёт: 'org' — организация, 'person' —
# человек.
TEMPLATES = [
    ('Ремонт кровли производственного цеха', 'org', [
        ('Обследовать кровлю и составить дефектную ведомость', 4, ['Сфотографировать протечки', 'Замерить площадь']),
        ('Согласовать смету с бухгалтерией', 3, []),
        ('Заказать мембрану и утеплитель', 6, ['Сверить спецификацию', 'Оплатить счёт']),
        ('Демонтировать старое покрытие', 5, []),
        ('Уложить утеплитель и мембрану', 9, ['Проверить уклоны', 'Сделать примыкания']),
        ('Принять работы и закрыть акт', 2, []),
    ]),
    ('Переход на электронный документооборот', 'org', [
        ('Выбрать оператора ЭДО', 5, ['Сравнить тарифы', 'Проверить роуминг с контрагентами']),
        ('Выпустить подпись руководителю', 3, []),
        ('Разослать приглашения контрагентам', 7, ['Составить список из учёта', 'Обзвонить крупных']),
        ('Настроить маршруты согласования', 4, []),
        ('Перевести поставщиков на ЭДО', 21, []),
        ('Отказаться от бумажных счетов-фактур', 10, []),
    ]),
    ('Открытие пункта выдачи заказов', 'org', [
        ('Подобрать помещение у остановки', 10, ['Осмотреть три варианта', 'Договориться об аренде']),
        ('Сделать ремонт и вывеску', 14, ['Покрасить стены', 'Заказать вывеску']),
        ('Закупить стеллажи и сканер', 5, []),
        ('Нанять двух операторов', 12, ['Разместить вакансию', 'Провести собеседования']),
        ('Открыться и провести неделю скидок', 7, []),
    ]),
    ('Внедрение складского учёта', 'org', [
        ('Описать текущие остатки', 6, ['Провести инвентаризацию', 'Разметить ячейки']),
        ('Завести номенклатуру в учёт', 8, []),
        ('Настроить приёмку и отгрузку', 5, []),
        ('Обучить кладовщиков', 3, ['Составить памятку', 'Провести занятие']),
        ('Сверить остатки через месяц', 30, []),
    ]),
    ('Энергоаудит и замена освещения', 'org', [
        ('Замерить потребление по цехам', 7, []),
        ('Составить отчёт энергоаудита', 5, []),
        ('Закупить светодиодные светильники', 6, ['Запросить три предложения', 'Оплатить счёт']),
        ('Заменить светильники в цехах', 10, []),
        ('Сравнить счета за электричество', 30, []),
    ]),
    ('Подготовка к сезону заготовки', 'org', [
        ('Проверить технику и тару', 5, ['Осмотреть сушилку', 'Пересчитать ящики']),
        ('Заключить договоры со сборщиками', 10, []),
        ('Согласовать цены закупки у населения', 4, []),
        ('Организовать приёмные пункты в сёлах', 12, ['Договориться с администрацией', 'Развезти весы']),
        ('Вывезти первую партию на переработку', 6, []),
    ]),
    ('Сертификация продукции', 'org', [
        ('Собрать пакет документов', 8, []),
        ('Отправить образцы в лабораторию', 4, []),
        ('Получить протоколы испытаний', 20, []),
        ('Подать декларацию в реестр', 5, []),
        ('Обновить этикетку', 6, ['Согласовать макет', 'Заказать тираж']),
    ]),
    ('Годовое общее собрание пайщиков', 'org', [
        ('Утвердить повестку на правлении', 3, []),
        ('Разослать уведомления пайщикам', 14, ['Подготовить бюллетени', 'Отправить письма']),
        ('Подготовить отчёт ревизионной комиссии', 10, []),
        ('Провести собрание', 1, ['Зарегистрировать участников', 'Подсчитать голоса']),
        ('Оформить протокол и внести изменения', 7, []),
    ]),
    ('Ремонт квартиры под сдачу', 'person', [
        ('Составить план ремонта и бюджет', 3, []),
        ('Заменить проводку', 6, ['Купить кабель', 'Вызвать электрика']),
        ('Выровнять стены и поклеить обои', 10, []),
        ('Заменить сантехнику', 4, []),
        ('Сфотографировать и разместить объявление', 2, []),
    ]),
    ('Фестиваль соседских огородов', 'person', [
        ('Договориться о площадке с управой', 7, []),
        ('Собрать участников и мастер-классы', 14, ['Обзвонить огородников', 'Составить программу']),
        ('Найти спонсоров на призы', 10, []),
        ('Подготовить афишу и рассылку', 5, []),
        ('Провести фестиваль', 1, []),
        ('Подвести итоги и разослать фото', 3, []),
    ]),
    ('Курс «Учёт для небольшого кооператива»', 'person', [
        ('Составить программу из восьми занятий', 6, []),
        ('Записать видео первых занятий', 14, ['Написать сценарий', 'Смонтировать']),
        ('Набрать группу', 10, []),
        ('Провести занятия', 28, []),
        ('Собрать отзывы и поправить программу', 5, []),
    ]),
    ('Строительство бани на участке', 'person', [
        ('Сделать проект и заказать сруб', 8, []),
        ('Залить ленточный фундамент', 7, ['Выкопать траншею', 'Заказать бетон']),
        ('Собрать сруб и крышу', 12, []),
        ('Поставить печь и дымоход', 5, []),
        ('Отделать парилку', 9, []),
    ]),
    ('Перевод семейного бюджета в таблицу', 'person', [
        ('Собрать выписки за год', 3, []),
        ('Разложить траты по статьям', 5, []),
        ('Настроить ежемесячный отчёт', 2, []),
    ]),
    ('Сбор гуманитарной помощи в приют', 'person', [
        ('Узнать у приюта, что нужно', 2, []),
        ('Объявить сбор в сообществе', 3, []),
        ('Организовать пункт приёма', 10, ['Договориться с магазином', 'Поставить коробки']),
        ('Отвезти собранное', 1, []),
    ]),
]

# Как проект без сбора распределён по состояниям: (код, доля).
STATES = [('empty', 0.10), ('preparation', 0.12), ('supply', 0.12),
          ('work', 0.22), ('acceptance', 0.08), ('settlement', 0.24),
          ('stopped', 0.12)]


def load_project_work(env):
    stages = load_project_tasks._ensure_stages(
        env['project.task.type'].sudo(), env['project.project'].sudo())
    tags = load_project_tasks._ensure_tags(env)
    _archive_stubs(env)
    _drop_system_user(env)
    # У каждого прохода свой генератор: иначе повторный прогон, где
    # первый проход уже ничего не делает, сдвинул бы случайности второго.
    made = _load_free_projects(env, random.Random(20261008), stages, tags)
    fixed = _repair_fee_tasks(env, random.Random(452), stages)
    # «Теплица» ушла из этапа «New» только сейчас — снимаем его здесь,
    # а не ждём следующего обновления модуля проектов.
    env['project.project'].coop_drop_engine_stages()
    _logger.info('Управление проектами: проектов без сбора заведено %s, '
                 'проектов сборов доведено %s', made, fixed)
    return made, fixed


# ── Общее ──────────────────────────────────────────────────────────────

def _at(day, hour=18):
    return datetime.combine(day, time(hour, 0))


def _project_values(env, name, partner, user, stages):
    """Обязательные поля проекта — как у `_create_managed_project`.

    Этапы задач — общие для всех проектов платформы: без привязки у
    проекта на канбане нет ни одного столбца.
    """
    Project = env['project.project'].sudo()
    values = {
        'name': name,
        'type_ids': [(6, 0, list(stages.values()))],
        'partner_id': partner.id,
        'label_tasks': 'Задачи',
        'privacy_visibility': 'followers',
        'allow_milestones': True,
        'allow_task_dependencies': True,
    }
    if user:
        values['user_id'] = user.id
    if 'billing_type' in Project._fields:
        values['billing_type'] = 'not_billable'
    for fname, field in Project._fields.items():
        if fname in values or not field.store or field.type != 'selection':
            continue
        if (field.compute and field.readonly) or not field.required:
            continue
        default = field.default(Project) if callable(field.default) else field.default
        options = [code for code, _label in (field.selection or [])]
        values[fname] = default or (options[0] if options else False)
    return values


def _attachment(env, task, filename, kind, rnd, project_name):
    if kind == 'smeta':
        rows = ['Статья;Кол-во;Цена, ₽;Сумма, ₽']
        for item in ('Материалы', 'Доставка', 'Работы подрядчика', 'Резерв 5%'):
            qty = rnd.randint(1, 40)
            price = rnd.randint(8, 400) * 100
            rows.append('%s;%s;%s;%s' % (item, qty, price, qty * price))
        body = '\n'.join(rows)
    elif kind == 'offers':
        rows = ['Поставщик;Цена, ₽;Срок, дней;Оплата']
        for name in ('ООО «СтройРесурс»', 'ИП Карпов', 'ПК «Снабженец»'):
            rows.append('%s;%s;%s;%s' % (name, rnd.randint(90, 160) * 1000,
                                         rnd.randint(5, 30),
                                         rnd.choice(['предоплата 50%', 'по факту', 'отсрочка 14 дней'])))
        body = '\n'.join(rows)
    elif kind == 'act':
        body = ('Акт приёмки работ по проекту «%s»\n\nРаботы выполнены в полном '
                'объёме, замечаний нет.\nПодписи вкладчиков приложены.\n'
                % project_name)
    else:
        body = ('Товарная накладная № %s\nПолучено полностью, '
                'расхождений нет.\n' % rnd.randint(100, 9999))
    env['ir.attachment'].sudo().create({
        'name': filename,
        'res_model': 'project.task',
        'res_id': task.id,
        'datas': base64.b64encode(body.encode('utf-8')),
        'mimetype': 'text/csv' if filename.endswith('.csv') else 'text/plain',
    })


def _subtasks(env, parent, titles, rnd, stages, hours_per_day):
    Task = env['project.task'].sudo()
    for index, title in enumerate(titles):
        if parent.state == '1_done':
            stage, state = stages['done'], '1_done'
        elif parent.state == '1_canceled':
            stage, state = parent.stage_id.id, '1_canceled'
        elif index == 0 and parent.stage_id.id != stages['idea']:
            stage, state = stages['done'], '1_done'
        else:
            stage, state = parent.stage_id.id, '01_in_progress'
        Task.create({
            'name': title,
            'project_id': parent.project_id.id,
            'parent_id': parent.id,
            'stage_id': stage,
            'state': state,
            'user_ids': [(6, 0, parent.user_ids.ids)],
            'date_deadline': parent.date_deadline,
            'allocated_hours': round(hours_per_day * rnd.uniform(0.5, 2.0)),
            'sequence': index + 1,
        })


def _close(task, rnd):
    """Закрыть задачу датой чуть раньше срока, иногда — позже."""
    if task.date_deadline:
        task.date_end = task.date_deadline + timedelta(days=rnd.randint(-4, 2))


# ── 1. Задачи проектов сборов ──────────────────────────────────────────

def _repair_fee_tasks(env, rnd, stages):
    Task = env['project.task'].sudo()
    today = fields.Date.today()
    fixed = 0
    for collect in env['coop.project'].sudo().search(
            [('project_id', '!=', False)], order='id'):
        project = collect.project_id
        tasks = Task.search([('project_id', '=', project.id),
                             ('parent_id', '=', False)], order='sequence, id')
        if not tasks or any(tasks.mapped('allocated_hours')):
            continue
        dated = tasks.filtered('date_deadline')
        if not dated:
            continue
        # Опорная точка: у завершённого — последний срок, у идущего —
        # первая незакрытая задача. Она встаёт около сегодняшнего дня.
        open_tasks = dated.filtered(lambda t: t.stage_id.id != stages['done'])
        if collect.state == 'done' or not open_tasks:
            pivot = max(dated.mapped('date_deadline')).date()
            target = today - timedelta(days=rnd.randint(20, 200))
        else:
            pivot = open_tasks[0].date_deadline.date()
            target = today + timedelta(days=rnd.randint(-25, 20))
        shift = target - pivot
        for task in dated:
            task.date_deadline = task.date_deadline + shift

        previous = None
        for task in tasks:
            days = 7
            if previous and previous.date_deadline and task.date_deadline:
                days = max(2, (task.date_deadline - previous.date_deadline).days)
            hours_per_day = rnd.choice([2, 3, 4, 6])
            vals = {'allocated_hours': days * hours_per_day}
            if task.stage_id.id == stages['done']:
                vals['state'] = '1_done'
            elif task.stage_id.id == stages['review']:
                vals['state'] = rnd.choice(['01_in_progress', '02_changes_requested',
                                            '03_approved'])
            elif task.stage_id.id == stages['idea'] and rnd.random() < 0.08:
                vals['state'] = '1_canceled'
            task.write(vals)
            if task.state == '1_done':
                _close(task, rnd)
            # Цепочка: следующий шаг ждёт предыдущего — не везде, а там,
            # где без него действительно не начать.
            if previous and rnd.random() < 0.6:
                task.depend_on_ids = [(4, previous.id)]
            for prefix, titles in SUBTASKS.items():
                if task.name.startswith(prefix) and rnd.random() < 0.7:
                    _subtasks(env, task, titles, rnd, stages, hours_per_day)
                    break
            for prefix, (filename, kind) in ATTACH.items():
                if task.name.startswith(prefix) and (
                        kind != 'act' or task.state == '1_done'):
                    _attachment(env, task, filename, kind, rnd, project.name)
                    break
            previous = task
        project.write({
            'allow_task_dependencies': True,
            'date_start': min(tasks.filtered('date_deadline').mapped(
                'date_deadline')).date() - timedelta(days=7),
            'date': max(tasks.filtered('date_deadline').mapped('date_deadline')).date(),
        })
        fixed += 1
    return fixed


def _drop_system_user(env):
    """Системного пользователя — с задач и из команд.

    Первый прогон 08.10.2026 заводил свободные задачи без явного
    исполнителя, и движок ставил на них того, кто создаёт, — системного
    пользователя (52 задачи, 47 команд).
    """
    system = env.ref('base.user_root')
    tasks = env['project.task'].sudo().with_context(active_test=False).search(
        [('user_ids', 'in', system.id)])
    if tasks:
        tasks.write({'user_ids': [(3, system.id)]})
    Project = env['project.project'].sudo().with_context(active_test=False)
    # Руководителем проекта организации вставал системный пользователь:
    # у организации нет своего входа. Ставим её представителя.
    for project in Project.search([('user_id', '=', system.id)]):
        lead = (project.partner_id.user_ids
                or Project._coop_partner_users(project.partner_id))[:1]
        project.user_id = lead.id or False
    projects = Project.search([('allowed_internal_user_ids', 'in', system.id)])
    if projects:
        projects.write({'allowed_internal_user_ids': [(3, system.id)]})
    if tasks or projects:
        _logger.info('Системный пользователь снят: задач %s, команд %s',
                     len(tasks), len(projects))


# ── 2. Заглушки ────────────────────────────────────────────────────────

def _archive_stubs(env):
    """Проекты без владельца, без задач и без сбора — в архив.

    «Строительный 3D-принтер» и «Кооперативный склад» завела система
    07.10.2026 при установке: ни инициатора, ни задач, видны всем.
    """
    Project = env['project.project'].sudo()
    linked = env['coop.project'].sudo().search(
        [('project_id', '!=', False)]).project_id
    internal = env['res.company'].sudo().search([]).internal_project_id
    stubs = Project.search([
        ('id', 'not in', (linked | internal).ids),
        ('partner_id', '=', False),
        ('task_ids', '=', False),
    ])
    if stubs:
        stubs.write({'active': False})
        _logger.info('Заглушки проектов в архив: %s', ', '.join(stubs.mapped('name')))


# ── 3. Проекты без сбора ──────────────────────────────────────────────

def _owners(env):
    """Организации с руководителем и людьми; люди — внутренние участники."""
    Membership = env['coop.membership'].sudo()
    heads = Membership.search([('state', '=', 'active'),
                               ('power_ids.code', '=', 'sign'),
                               ('organization_id.is_company', '=', True),
                               ('partner_id.user_ids', '!=', False)], order='id')
    orgs = []
    seen = set()
    for membership in heads:
        org = membership.organization_id
        if org.id in seen:
            continue
        seen.add(org.id)
        staff = Membership.search([('organization_id', '=', org.id),
                                   ('state', '=', 'active')]).partner_id.user_ids
        staff = staff.filtered(lambda u: not u.share and u.active)
        if staff:
            orgs.append((org, membership.partner_id.user_ids[:1], staff))
    people = env['res.users'].sudo().search(
        [('share', '=', False), ('active', '=', True), ('id', '>', 2)], order='id')
    return orgs, people


def _load_free_projects(env, rnd, stages, tags):
    Project = env['project.project'].sudo()
    today = fields.Date.today()
    orgs, people = _owners(env)
    if not orgs or not people:
        return 0
    project_stages = {}
    for key in ('preparation', 'supply', 'work', 'acceptance', 'settlement', 'stopped'):
        stage = env.ref('coop_projects.project_stage_%s' % key, raise_if_not_found=False)
        if stage:
            project_stages[key] = stage.id

    _greenhouse(env, random.Random(57), stages, project_stages)

    plan = []
    for copy in range(5):
        for template in TEMPLATES:
            plan.append(template)
    rnd.shuffle(plan)
    plan = plan[:64]
    states = []
    for code, share in STATES:
        states += [code] * round(share * len(plan))
    states = (states + ['work'] * len(plan))[:len(plan)]
    rnd.shuffle(states)

    # Названия — заранее и одним куском: повторный прогон узнаёт свои
    # проекты по названию, и оно не должно зависеть от того, сколько
    # случайностей съели проекты, заведённые в прошлый раз.
    names = []
    for title, _kind, _steps in plan:
        name = '%s — %s' % (title, rnd.choice(CITIES))
        while name in names:
            name = '%s — %s' % (title, rnd.choice(CITIES))
        names.append(name)

    made = 0
    org_index = 0
    used = set(Project.with_context(active_test=False).search([]).mapped('name'))
    for name, (title, kind, steps), state in zip(names, plan, states):
        if name in used:
            org_index += 7
            continue
        used.add(name)
        if kind == 'org':
            org, head, staff = orgs[org_index % len(orgs)]
            org_index += 7
            partner, lead, crew = org, head or staff[:1], staff
        else:
            lead = people[rnd.randrange(len(people))]
            partner = lead.partner_id
            crew = lead | people.browse(rnd.sample(people.ids, 3))
        with env.cr.savepoint():
            project = Project.create(_project_values(env, name, partner, lead, stages))
            project.message_subscribe(partner_ids=partner.ids)
            project._coop_add_team(lead | crew
                                   | project._coop_partner_users(partner))
            if kind == 'org' and not partner.coop_app_project:
                partner.sudo().coop_app_project = True
            _fill_free_project(env, project, steps, state, crew, rnd, stages,
                               tags, project_stages, today)
            made += 1
    return made


def _fill_free_project(env, project, steps, state, crew, rnd, stages, tags,
                       project_stages, today):
    Task = env['project.task'].sudo()
    stage_key = {'empty': 'preparation'}.get(state, state)
    if stage_key in project_stages:
        project.stage_id = project_stages[stage_key]
    if state == 'empty':
        project.date_start = today + timedelta(days=rnd.randint(5, 60))
        return
    total = sum(days for _t, days, _s in steps)
    if state == 'settlement':
        start = today - timedelta(days=total + rnd.randint(15, 220))
        progress = 1.0
    elif state == 'stopped':
        start = today - timedelta(days=rnd.randint(60, 250))
        progress = rnd.uniform(0.2, 0.6)
    else:
        progress = {'preparation': 0.05, 'supply': 0.3, 'work': 0.55,
                    'acceptance': 0.85}[state] + rnd.uniform(-0.05, 0.1)
        start = today - timedelta(days=int(total * progress) + rnd.randint(-10, 10))
    project.date_start = start
    project.date = start + timedelta(days=total + rnd.randint(0, 20))

    offset = 0
    previous = None
    for order, (title, days, subtitles) in enumerate(steps):
        deadline = start + timedelta(days=offset + days)
        point = (offset + days) / float(total)
        offset += days
        if point <= progress:
            stage, task_state = stages['done'], '1_done'
        elif point - progress < 0.15:
            stage = stages['review'] if rnd.random() < 0.4 else stages['doing']
            task_state = '01_in_progress'
        elif point - progress < 0.4:
            stage, task_state = stages['doing'], '01_in_progress'
        else:
            stage, task_state = stages['idea'], '01_in_progress'
        if state == 'stopped' and task_state != '1_done':
            task_state = '1_canceled'
        hours_per_day = rnd.choice([2, 3, 4, 6])
        values = {
            'name': title,
            'project_id': project.id,
            'stage_id': stage,
            'state': task_state,
            'sequence': (order + 1) * 10,
            'date_deadline': _at(deadline),
            'allocated_hours': days * hours_per_day,
            'tag_ids': [(6, 0, [tags[rnd.choice(load_project_tasks.TAGS)]])],
            'priority': '1' if rnd.random() < 0.15 else '0',
            # Пусто явно: иначе движок подставит того, кто создаёт, — а
            # загрузчик работает от системного пользователя.
            'user_ids': [(6, 0, [])],
        }
        # Задача без исполнителя — тоже правда жизни: её ещё не взяли.
        if rnd.random() < 0.88:
            values['user_ids'] = [(6, 0, [crew[order % len(crew)].id])]
        task = Task.create(values)
        if task_state == '1_done':
            _close(task, rnd)
        if previous and rnd.random() < 0.55:
            task.depend_on_ids = [(4, previous.id)]
        if subtitles:
            _subtasks(env, task, subtitles, rnd, stages, hours_per_day)
        previous = task


def _greenhouse(env, rnd, stages, project_stages):
    """Демо-«Теплица» из XML — в настоящий проект кооператива «Шукты»."""
    project = env.ref('coop_demo.project_greenhouse', raise_if_not_found=False)
    if not project or project.privacy_visibility == 'followers':
        return
    project = project.sudo()
    org = project.partner_id
    staff = env['coop.membership'].sudo().search([
        ('organization_id', '=', org.id), ('state', '=', 'active')]).partner_id.user_ids
    staff = staff.filtered(lambda u: not u.share and u.active)
    project.write({'privacy_visibility': 'followers', 'label_tasks': 'Задачи',
                   'allow_task_dependencies': True, 'allow_milestones': True,
                   'type_ids': [(6, 0, list(stages.values()))],
                   'stage_id': project_stages.get('work', project.stage_id.id),
                   'user_id': staff[:1].id or False})
    project.message_subscribe(partner_ids=org.ids)
    project._coop_add_team(staff | project._coop_partner_users(org))
    today = fields.Date.today()
    plan = [(stages['done'], '1_done', -40), (stages['doing'], '01_in_progress', 6),
            (stages['idea'], '01_in_progress', 30)]
    previous = None
    for task, (stage, state, days) in zip(
            project.task_ids.sorted('id'), plan):
        task.write({'stage_id': stage, 'state': state,
                    'date_deadline': _at(today + timedelta(days=days)),
                    'allocated_hours': rnd.choice([24, 40, 56]),
                    'user_ids': [(6, 0, staff[:2].ids)] if staff else False})
        if state == '1_done':
            _close(task, rnd)
        if previous:
            task.depend_on_ids = [(4, previous.id)]
        previous = task
    if not org.coop_app_project:
        org.sudo().coop_app_project = True

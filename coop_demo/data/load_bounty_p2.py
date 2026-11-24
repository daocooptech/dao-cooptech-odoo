# -*- coding: utf-8 -*-
"""Задачи П2 (№ 465): постоянные, командные, частичные и споры исполнителя.

Каждая — тем же путём, что в жизни: публикация с резервом, заявки,
утверждение в команду, сдачи, приёмка с выплатами. Загрузчик идёт при
каждой выкатке, поэтому задача с таким названием уже есть — пропускаем.
"""
import logging
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError

from .load_bounty import RETURN_NOTES, SUBMIT_NOTES, _link, _performers
from .demo_only import DEMO

_logger = logging.getLogger(__name__)

# Постоянные задачи: название, специализация, сумма, лимит, принято,
# на проверке, возвращено, отменена ли автором.
RECURRING_PLATFORM = [
    ('Найти ошибку на экране платформы и описать шаги', 'Программирование, Разработка',
     60, 20, 9, 3, 2, False),
    ('Перевести страницу справки на английский', 'Переводчик', 80, 12, 5, 2, 1, False),
    ('Вычитать раздел интерфейса: опечатки и канцелярит', 'Переводчик', 40, 15, 15, 0, 1, False),
    ('Записать короткое видео: как пользоваться разделом', 'Дизайн, графика', 150, 6, 2, 1, 1, False),
    ('Привести организацию на платформу и помочь с первым объявлением', 'Бизнес-консультант',
     200, 10, 4, 2, 0, False),
    ('Ответить на вопрос участника по закону со ссылкой на статью', 'Юрисконсульт',
     120, 8, 3, 1, 1, False),
    ('Проверить расчёт раздела на примере из базы', 'Бухгалтерия', 100, 6, 0, 2, 0, False),
    ('Нарисовать иллюстрацию для пустого состояния экрана', 'Дизайн, графика', 90, 10, 6, 0, 2, True),
]
RECURRING_PROJECT = [
    ('Сфотографировать продукцию на точке выдачи', 'Дизайн, графика', 150, 12, 4, 2, 1),
    ('Отзыв покупателя с фото — для страницы проекта', 'Журналистика, СМИ', 80, 20, 7, 1, 2),
    ('Привести покупателя в совместную закупку', 'Бизнес-консультант', 250, 15, 3, 2, 0),
    ('Перевести карточку товара для зарубежного покупателя', 'Переводчик', 120, 8, 8, 0, 0),
]
RECURRING_DESCRIPTION = (
    'Постоянная задача: результат сдаёт любой участник без заявки, каждый принятый '
    'результат оплачивается, пока не исчерпан лимит. %s')

# Командные: название, кто платит, специализация, сумма, исполнителей,
# утвердить, частичная шкала, итог, доли.
TEAMS = [
    ('Сверстать раздел «Аукционы» по дизайн-системе', 'platform', 'Программирование, Разработка',
     600, 3, 3, 0, 'accepted', None),
    ('Правовой разбор договора займа между кооперативами', 'platform', 'Юрисконсульт',
     400, 2, 2, 50, 'accepted', (60, 40)),
    ('Перевести интерфейс кабинета на казахский', 'platform', 'Переводчик',
     500, 3, 3, 40, 'assigned', None),
    ('Аналитика закупок за квартал: отчёт и выводы', 'platform', 'Аналитика, Data Science',
     300, 2, 1, 0, 'published', None),
    ('Фотосессия для каталога продукции', 'project', 'Дизайн, графика',
     900, 2, 2, 50, 'submitted', (50, 50)),
    ('Ремонт помещения точки выдачи', 'project', 'Бизнес-консультант',
     1500, 4, 3, 0, 'started', None),
    ('Упаковка и маркировка партии к ярмарке', 'project', 'Дизайн, графика',
     600, 3, 3, 50, 'partial', None),
    ('Сайт кооператива на конструкторе платформы', 'project', 'Программирование, Разработка',
     1200, 2, 0, 30, 'published', None),
]

# Частичная приёмка и споры исполнителя: название, специализация, сумма,
# шкала, итог.
SINGLES = [
    ('Схема проезда к складу для карточки организации', 'Дизайн, графика', 120, 50, 'partial'),
    ('Таблица тарифов доставки по городам', 'Аналитика, Data Science', 180, 40, 'partial'),
    ('Памятка пайщику о налоге с вознаграждения', 'Бухгалтерия', 150, 60, 'partial'),
    ('Подборка вопросов для собеседования волонтёра', 'Бизнес-консультант', 90, 30, 'partial'),
    ('Перевести условия пользования на английский', 'Переводчик', 220, 50, 'dispute_open'),
    ('Сценарий вебинара «Кооператив за вечер»', 'Журналистика, СМИ', 160, 40, 'dispute_open'),
    ('Шаблон устава потребительского общества', 'Юрисконсульт', 300, 50, 'dispute_partial'),
    ('Иконки для раздела «Склады»', 'Дизайн, графика', 140, 0, 'cancel_dispute'),
    ('Выгрузка остатков склада в таблицу', 'Программирование, Разработка', 200, 0, 'cancel_closed'),
    ('Тексты подсказок для формы организации', 'Журналистика, СМИ', 110, 50, 'can_dispute'),
]
EXECUTOR_REASONS = [
    'Результат трижды сдан по критериям, замечания каждый раз новые — прошу разобрать.',
    'Задачу отменили через день после сдачи, результат приложен и соответствует описанию.',
    'Все пункты приёмки выполнены, автор возвращает без ссылки на критерии.',
]
PARTIAL_DECISIONS = [
    'Первый критерий выполнен полностью, второй — нет: засчитано частично, по шкале задачи.',
    'Основной результат сдан, исходники не переданы. Засчитано частично.',
]
CANCEL_DECISIONS = [
    'Результат не соответствует описанию задачи и не доработан после замечаний. Отмена оставлена в силе.',
]


def _criteria(text):
    return [(0, 0, {'name': 'Результат соответствует описанию задачи', 'sequence': 10}),
            (0, 0, {'name': text, 'sequence': 20})]


def _create(Task, values):
    """Создать и опубликовать; фонда не хватило — пропустить задачу."""
    try:
        with Task.env.cr.savepoint():
            task = Task.create(values)
            task.action_publish()
        return task
    except UserError as error:
        _logger.warning('Задача П2 «%s» не опубликована: %s', values['name'], error)
        return None


def _backdate(task, start, step=3):
    """Сдачи и выплаты — вразброс по прошлым неделям, а не в один день."""
    today = fields.Date.context_today(task)
    for number, sub in enumerate(task.submission_ids.sorted('id')):
        day = today - timedelta(days=start - number * step)
        if day > today:
            day = today
        values = {'date': day}
        if sub.reviewed_on:
            values['reviewed_on'] = min(day + timedelta(days=number % 4), today)
        sub.write(values)
        sub.payout_ids.write({'date': values.get('reviewed_on', day)})


def _recurring(env, Task, base, rows, people, start_index):
    Submission = env['coop.bounty.submission'].sudo()
    created = 0
    for index, row in enumerate(rows, start=start_index):
        name, accepted, review, returned, cancel = row[0], row[4], row[5], row[6], row[7]
        values = dict(base(row), name=name, is_recurring=True, repeat_limit=row[3],
                      reward_tokens=row[2], partial_percent=0)
        task = _create(Task, values)
        if not task:
            continue
        created += 1
        crowd = [people[(index * 3 + k) % len(people)] for k in range(accepted + review + returned)]
        for number, partner in enumerate(crowd):
            sub = Submission.create({
                'task_id': task.id, 'partner_id': partner.id, 'version': 1,
                'link': _link(task, number + 1),
                'note': SUBMIT_NOTES[(index + number) % len(SUBMIT_NOTES)]})
            if number < accepted:
                sub.action_accept_result()
            elif number >= accepted + review:
                sub.write({'state': 'returned', 'reviewed_on': fields.Date.context_today(sub),
                           'review_note': RETURN_NOTES[(index + number) % len(RETURN_NOTES)]})
        _backdate(task, 6 + len(crowd) * 3)
        if cancel and task.state == 'published':
            task.action_cancel()
    return created


def load_bounty_p2(env, Task, manager, specializations):
    people = env['res.partner'].sudo().search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)], order='id', limit=60)
    performers, _showcase = _performers(env, people)
    # Витринный человек бывает и среди участников — без повторов.
    seen = set()
    performers = [p for p in performers if not (p.id in seen or seen.add(p.id))]
    if len(performers) < 6:
        return 0
    method = {m.code: m for m in env['coop.bounty.method'].sudo().with_context(
        active_test=False).search([])}
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    projects = env['coop.project'].sudo().search(
        DEMO + [('coop_token_name', '!=', False), ('partner_id.is_company', '=', True)]
        + ([('id', '!=', ours.id)] if ours else []), order='id', limit=12)
    existing = set(Task.search([]).mapped('name'))
    today = fields.Date.context_today(Task)
    spec = lambda name: specializations.get(name).id if specializations.get(name) else False

    def platform(row):
        return {'payer_id': env.company.partner_id.id, 'project_id': ours.id if ours else False,
                'description': '<p>%s</p>' % (RECURRING_DESCRIPTION % row[0]),
                'coop_specialization_id': spec(row[1]), 'manager_id': manager.id,
                'allowed_method_ids': [(6, 0, [method['tokens'].id])],
                'criterion_ids': _criteria('Результат приложен к сдаче, его можно проверить')}

    def project_values(row, number):
        project = projects[number % len(projects)]
        return {'payer_id': project.partner_id.id, 'project_id': project.id,
                'description': '<p>%s</p>' % (RECURRING_DESCRIPTION % row[0]),
                'coop_specialization_id': spec(row[1]), 'manager_id': manager.id,
                'allowed_method_ids': [(6, 0, [method['project_tokens'].id])],
                'criterion_ids': _criteria('Результат приложен к сдаче, его можно проверить')}

    created = 0
    rows = [r for r in RECURRING_PLATFORM if r[0] not in existing]
    created += _recurring(env, Task, platform, rows, performers, 0)
    if projects:
        rows = [r + (False,) for r in RECURRING_PROJECT if r[0] not in existing]
        numbered = {r[0]: n for n, r in enumerate(RECURRING_PROJECT)}
        created += _recurring(env, Task, lambda r: project_values(r, numbered[r[0]]),
                              rows, performers, 20)

    # Команды.
    for index, (name, kind, specialization, reward, limit, approve, partial, outcome, shares) \
            in enumerate(TEAMS):
        if name in existing or (kind == 'project' and not projects):
            continue
        row = (name, specialization)
        values = platform(row) if kind == 'platform' else project_values(row, index)
        values.update(name=name, reward_tokens=reward, executor_limit=limit, partial_percent=partial,
                      description='<p>Командная задача: сумма делится между исполнителями, '
                                  'результат за команду сдаёт первый утверждённый.</p>',
                      deadline=today + timedelta(days=10 + index * 3))
        task = _create(Task, values)
        if not task:
            continue
        created += 1
        team = [performers[(index * 2 + k + 1) % len(performers)] for k in range(limit + 1)]
        if index == 0:
            team[0] = performers[0]
        applications = env['coop.bounty.application'].sudo()
        for number, partner in enumerate(team):
            applications |= env['coop.bounty.application'].sudo().create({
                'task_id': task.id, 'partner_id': partner.id,
                'method_id': task.allowed_method_ids[:1].id,
                'message': 'Готов работать в команде, делал похожее.'})
        for application in applications[:approve]:
            application.action_approve()
        if outcome == 'started' and task.state == 'published':
            task._coop_team_ready()
        if shares and len(task.member_ids) == len(shares):
            for member, share in zip(task.member_ids, shares):
                member.share_percent = share
        if outcome in ('submitted', 'accepted', 'partial') and task.state == 'assigned':
            task._coop_do_submit(_link(task, 1), SUBMIT_NOTES[index % len(SUBMIT_NOTES)])
            if outcome == 'accepted':
                task.criterion_ids.write({'done': True})
                task.action_accept()
            elif outcome == 'partial':
                task.criterion_ids[:1].write({'done': True})
                task.with_context(coop_bounty_partial=True).action_accept()
            _backdate(task, 5 + index)

    # Частичная приёмка и споры исполнителя.
    for index, (name, specialization, reward, partial, outcome) in enumerate(SINGLES):
        if name in existing:
            continue
        values = platform((name, specialization))
        values.update(name=name, reward_tokens=reward, partial_percent=partial,
                      description='<p>%s. Готово, когда результат проверен по критериям.</p>' % name,
                      deadline=today + timedelta(days=12 + index))
        task = _create(Task, values)
        if not task:
            continue
        created += 1
        executor = performers[0] if outcome == 'can_dispute' else \
            performers[(index * 5 + 3) % len(performers)]
        env['coop.bounty.application'].sudo().create({
            'task_id': task.id, 'partner_id': executor.id,
            'method_id': task.allowed_method_ids[:1].id,
            'message': 'Возьмусь, делал похожее.'}).action_approve()
        rounds = 3 if outcome in ('dispute_open', 'dispute_partial', 'can_dispute') else 0
        for number in range(rounds):
            task._coop_do_submit(_link(task, number + 1), SUBMIT_NOTES[(index + number) % len(SUBMIT_NOTES)])
            task._coop_do_return(RETURN_NOTES[(index + number) % len(RETURN_NOTES)])
        reason = EXECUTOR_REASONS[index % len(EXECUTOR_REASONS)]
        if outcome == 'partial':
            task._coop_do_submit(_link(task, 1), SUBMIT_NOTES[index % len(SUBMIT_NOTES)])
            task.criterion_ids[:1].write({'done': True})
            task.with_context(coop_bounty_partial=True).action_accept()
        elif outcome in ('dispute_open', 'dispute_partial'):
            task.write({'state': 'dispute', 'dispute_on': today - timedelta(days=index % 4),
                        'dispute_by': 'executor', 'dispute_reason': reason})
            task.message_post(body='Исполнитель открыл спор: %s' % reason)
            if outcome == 'dispute_partial':
                decision = PARTIAL_DECISIONS[index % len(PARTIAL_DECISIONS)]
                task.write({'dispute_decision': decision})
                task.message_post(body='Решение по спору — засчитать частично: %s' % decision)
                task.with_context(coop_bounty_force_accept=True, coop_bounty_partial=True).action_accept()
        elif outcome in ('cancel_dispute', 'cancel_closed'):
            task._coop_do_submit(_link(task, 1), SUBMIT_NOTES[index % len(SUBMIT_NOTES)])
            task.action_cancel()
            task.write({'state': 'dispute', 'dispute_on': today, 'dispute_by': 'executor',
                        'dispute_reason': EXECUTOR_REASONS[1]})
            task.message_post(body='Исполнитель открыл спор: %s' % EXECUTOR_REASONS[1])
            if outcome == 'cancel_closed':
                decision = CANCEL_DECISIONS[0]
                task.write({'dispute_decision': decision})
                task.message_post(body='Решение по спору — отменить задачу: %s' % decision)
                task.with_context(coop_bounty_arbiter=True).action_cancel()
        _backdate(task, 12 + index, step=2)

    # Шкала частичной оплаты — у части открытых задач и черновиков; у
    # задач из списка платформы её нет: их условия ведёт рабочая группа.
    env.cr.execute("""
        UPDATE coop_bounty_task SET partial_percent = (ARRAY[30, 40, 50, 60])[id % 4 + 1]
         WHERE id % 3 = 0 AND COALESCE(partial_percent, 0) = 0
           AND state IN ('draft', 'published') AND is_recurring IS NOT TRUE
           AND COALESCE(executor_limit, 1) = 1 AND coop_source_ref IS NULL""")
    Task.invalidate_model(['partial_percent'])
    _logger.info('Задачи П2: заведено %s', created)
    return created

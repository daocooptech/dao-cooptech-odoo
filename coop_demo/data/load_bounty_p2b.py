# -*- coding: utf-8 -*-
"""Задачи П2, второй кусок (№ 465): конкурсы, этапы, резерв проекта.

Каждая — тем же путём, что в жизни: публикация с резервом (фонд у задач
нашего проекта, токены на задачи — у проектов), работы и сдачи, итог
конкурса, приёмка этапов с выплатами. Загрузчик идёт при каждой выкатке:
задача с таким названием уже есть — пропускаем.
"""
import logging
from datetime import timedelta

from odoo import fields

from .load_bounty import RETURN_NOTES, SUBMIT_NOTES, _link, _performers
from .load_bounty_p2 import _backdate, _create, _criteria

_logger = logging.getLogger(__name__)

# Конкурсы: название, чей (наш проект или проект), специализация, призы
# по местам, сколько работ, итог, дней назад закончился приём.
CONTESTS = [
    ('Логотип для раздела «Краудсорсинг»', 'platform', 'Дизайн, графика', (500, 300, 150), 7, 'open', 0),
    ('Слоган платформы для новичков', 'platform', 'Журналистика, СМИ', (300, 150), 9, 'done', 12),
    ('Иллюстрация для пустого каталога', 'platform', 'Дизайн, графика', (400,), 4, 'waiting', 2),
    ('Название для токена проекта', 'project', 'Журналистика, СМИ', (1000, 500), 12, 'done', 20),
    ('Этикетка для новой линейки продукции', 'project', 'Дизайн, графика', (3000, 1500, 750), 6, 'open', 0),
    ('Фотография продукции для обложки каталога', 'project', 'Дизайн, графика', (2000, 1000), 5, 'done', 8),
    ('Рецепт с продукцией кооператива для рассылки', 'project', 'Журналистика, СМИ',
     (800, 400, 200), 3, 'dispute', 12),
    ('Короткое видео о проекте — до минуты', 'project', 'Дизайн, графика', (2500,), 0, 'empty', 3),
    ('Макет вывески точки выдачи', 'project', 'Дизайн, графика', (1500, 700), 4, 'waiting', 1),
    ('Текст приглашения в совместную закупку', 'project', 'Бизнес-консультант',
     (600, 300, 150), 8, 'done_two', 6),
    ('Лучший перевод описания проекта на английский', 'project', 'Переводчик', (900,), 2, 'open', 0),
    ('Плакат к ярмарке кооперативов', 'project', 'Дизайн, графика', (1200, 600), 0, 'open', 0),
]
CONTEST_DESCRIPTION = (
    '<p>Конкурс: работы присылают без заявки до срока, присланную не меняют. Автор '
    'присуждает призовые места, итог получают все участники. %s.</p>')

# Этапные задачи: название, чей, специализация, этапы, частичная шкала, итог.
STAGED = [
    ('Сайт кооператива: макет, вёрстка, запуск', 'project', 'Программирование, Разработка',
     [('Макет', 8000), ('Вёрстка', 15000), ('Запуск', 7000)], 0, 'stage2'),
    ('Фирменный стиль: логотип, цвета, носители', 'project', 'Дизайн, графика',
     [('Логотип', 5000), ('Цвета и шрифты', 3000), ('Носители', 4000)], 0, 'accepted'),
    ('Каталог продукции: съёмка, обработка, вёрстка', 'project', 'Дизайн, графика',
     [('Съёмка', 6000), ('Обработка', 3000), ('Вёрстка каталога', 4000)], 0, 'stage1_review'),
    ('Бизнес-план расширения производства', 'project', 'Бизнес-консультант',
     [('Анализ рынка', 4000), ('Финансовая модель', 6000)], 0, 'published'),
    ('Мобильная витрина для точки выдачи', 'project', 'Программирование, Разработка',
     [('Прототип', 5000), ('Разработка', 12000), ('Публикация', 3000)], 0, 'stage1'),
    ('Перевод сайта проекта на три языка', 'project', 'Переводчик',
     [('Английский', 3000), ('Казахский', 3000), ('Китайский', 4000)], 0, 'stage2_review'),
    ('Устав и положения потребительского общества', 'project', 'Юрисконсульт',
     [('Устав', 6000), ('Положение о паях', 4000)], 0, 'dispute'),
    ('Учёт паевых взносов: настройка и обучение', 'project', 'Бухгалтерия',
     [('Настройка', 5000), ('Обучение', 2000)], 0, 'cancelled'),
    ('Видеоролик о проекте: сценарий, съёмка, монтаж', 'project', 'Дизайн, графика',
     [('Сценарий', 2000), ('Съёмка', 5000), ('Монтаж', 4000)], 50, 'partial'),
    ('Раздел справки платформы: структура и тексты', 'platform', 'Журналистика, СМИ',
     [('Структура', 300), ('Тексты', 600)], 0, 'accepted'),
    ('Аналитика продаж: выгрузка и отчёт', 'project', 'Аналитика, Data Science',
     [('Выгрузка', 2500), ('Отчёт', 3500)], 0, 'draft'),
]
STAGED_DESCRIPTION = (
    '<p>Крупная задача по этапам: у каждого этапа своя сумма, сдача и приёмка, принятый '
    'этап оплачивается сразу. %s.</p>')
SILENT_AUTHOR = 'Этап сдан, автор не отвечает больше недели — разберите, пожалуйста.'


def _room(project, need):
    """Проект выделяет токены на задачи, если свободных не хватает."""
    project.invalidate_recordset(['coop_bounty_blocked', 'coop_bounty_paid', 'coop_bounty_free'])
    used = project.coop_bounty_blocked + project.coop_bounty_paid
    limit = project.coop_bounty_token_limit
    if limit and limit - used >= need:
        return
    project.coop_bounty_token_limit = -(-int((used + need) * 1.25) // 1000) * 1000


def _tax_regimes(env):
    """Часть людей — самозанятые и ИП: автор видит статус до утверждения."""
    Partner = env['res.partner'].sudo().with_context(tracking_disable=True)
    if 'coop_tax_regime' not in Partner._fields:
        return 0
    changed = 0
    for partner in Partner.search([('coop_is_participant', '=', True), ('is_company', '=', False),
                                   ('coop_tax_regime', '=', 'none')]):
        slot = partner.id % 20
        regime = 'npd' if slot < 7 else 'usn_income' if slot < 10 else 'patent' if slot == 10 else False
        if regime:
            partner.coop_tax_regime = regime
            changed += 1
    return changed


def load_bounty_p2b(env, Task, manager, specializations):
    people = env['res.partner'].sudo().search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)], order='id', limit=80)
    performers, _showcase = _performers(env, people)
    seen = set()
    performers = [p for p in performers if not (p.id in seen or seen.add(p.id))]
    if len(performers) < 14:
        return 0
    _tax_regimes(env)
    method = {m.code: m for m in env['coop.bounty.method'].sudo().with_context(
        active_test=False).search([])}
    ours = env.ref('coop_bounty.project_cooptech', raise_if_not_found=False)
    projects = env['coop.project'].sudo().search(
        [('coop_token_name', '!=', False), ('partner_id.is_company', '=', True)]
        + ([('id', '!=', ours.id)] if ours else []), order='id', limit=12)
    if not projects:
        return 0
    existing = set(Task.search([]).mapped('name'))
    today = fields.Date.context_today(Task)
    Submission = env['coop.bounty.submission'].sudo()
    spec = lambda name: specializations.get(name).id if specializations.get(name) else False

    def base(name, kind, specialization, number, description):
        if kind == 'platform':
            values = {'payer_id': env.company.partner_id.id,
                      'project_id': ours.id if ours else False,
                      'allowed_method_ids': [(6, 0, [method['tokens'].id])]}
        else:
            project = projects[number % len(projects)]
            values = {'payer_id': project.partner_id.id, 'project_id': project.id,
                      'allowed_method_ids': [(6, 0, [method['project_tokens'].id])]}
        values.update(name=name, coop_specialization_id=spec(specialization),
                      manager_id=manager.id, description=description % name,
                      criterion_ids=_criteria('Результат приложен, его можно проверить по ссылке'))
        return values

    created = 0
    # ── Конкурсы ─────────────────────────────────────────────────────────
    for index, (name, kind, specialization, prizes, entries, outcome, ago) in enumerate(CONTESTS):
        if name in existing:
            continue
        values = base(name, kind, specialization, index, CONTEST_DESCRIPTION)
        values.update(is_contest=True, reward_tokens=sum(prizes),
                      deadline=today + timedelta(days=6 + index * 2),
                      prize_ids=[(0, 0, {'place': n + 1, 'amount': amount})
                                 for n, amount in enumerate(prizes)])
        if kind == 'project':
            _room(env['coop.project'].sudo().browse(values['project_id']), sum(prizes))
        task = _create(Task, values)
        if not task:
            continue
        created += 1
        crowd = [performers[(index * 5 + k + 1) % len(performers)] for k in range(entries)]
        if index in (0, 1) and entries:
            crowd[0] = performers[0]
        deadline = today - timedelta(days=ago) if ago else task.deadline
        for number, partner in enumerate(crowd):
            day = min(deadline - timedelta(days=entries - number), today)
            Submission.create({'task_id': task.id, 'partner_id': partner.id, 'version': 1,
                               'date': day, 'link': _link(task, number + 1),
                               'note': SUBMIT_NOTES[(index + number) % len(SUBMIT_NOTES)]})
        if outcome == 'open':
            continue
        task.deadline = deadline
        Task._cron_contest_deadline()
        if outcome in ('done', 'done_two') and task.state == 'submitted':
            subs = task.submission_ids.sorted('id')
            awarded = len(prizes) if outcome == 'done' else min(2, len(prizes))
            places = {sub: n + 1 for n, sub in enumerate(subs[:awarded])}
            task._coop_contest_finish(places)
            reviewed = min(deadline + timedelta(days=2 + index % 3), today)
            task.write({'accepted_on': reviewed})
            task.submission_ids.write({'reviewed_on': reviewed})
            task.payout_ids.write({'date': reviewed})

    # ── Этапные задачи ───────────────────────────────────────────────────
    for index, (name, kind, specialization, stages, partial, outcome) in enumerate(STAGED):
        if name in existing:
            continue
        values = base(name, kind, specialization, index + 3, STAGED_DESCRIPTION)
        values.update(partial_percent=partial, reward_tokens=sum(a for _n, a in stages),
                      deadline=today + timedelta(days=20 + index * 4),
                      stage_ids=[(0, 0, {'name': stage, 'amount': amount, 'sequence': (n + 1) * 10})
                                 for n, (stage, amount) in enumerate(stages)])
        if outcome == 'draft':
            Task.create(values)
            created += 1
            continue
        if kind == 'project':
            _room(env['coop.project'].sudo().browse(values['project_id']), values['reward_tokens'])
        task = _create(Task, values)
        if not task:
            continue
        created += 1
        if outcome == 'published':
            continue
        executor = performers[0] if index == 0 else performers[(index * 7 + 2) % len(performers)]
        env['coop.bounty.application'].sudo().create({
            'task_id': task.id, 'partner_id': executor.id,
            'method_id': task.allowed_method_ids[:1].id,
            'message': 'Сделаю по этапам, похожее уже делал.'}).action_approve()
        # Сколько этапов пройти до итогового состояния.
        plan = {'stage1': (0, False), 'stage1_review': (0, True), 'stage2': (1, False),
                'stage2_review': (1, True), 'accepted': (len(stages), False),
                'dispute': (0, True), 'cancelled': (1, False), 'partial': (1, False)}[outcome]
        for number in range(plan[0]):
            if number == 0 and index % 2:
                task._coop_do_submit(_link(task, 1), SUBMIT_NOTES[index % len(SUBMIT_NOTES)])
                task._coop_do_return(RETURN_NOTES[index % len(RETURN_NOTES)])
            task._coop_do_submit(_link(task, number + 2), SUBMIT_NOTES[(index + number) % len(SUBMIT_NOTES)])
            if number == len(stages) - 1:
                task.criterion_ids.write({'done': True})
            if outcome == 'partial':
                task.with_context(coop_bounty_partial=True).action_accept()
            else:
                task.action_accept()
        if plan[1]:
            task._coop_do_submit(_link(task, 9), SUBMIT_NOTES[index % len(SUBMIT_NOTES)])
        if outcome == 'dispute':
            # Автор молчит больше недели — спор откроет расписание.
            task.write({'submitted_on': today - timedelta(days=9)})
        elif outcome == 'cancelled':
            task.action_cancel()
        _backdate(task, 25 + index * 2, step=6)
    _logger.info('Задачи П2, кусок 2: заведено %s', created)
    return created

# -*- coding: utf-8 -*-
"""Табели витрины dashkevich — для штатных дашбордов «Расписания» и
«Проект» (решение 707, задача 494).

У «Вектор Инжиниринг» нет сотрудников и учёта времени. Здесь участники
организации с доступом к её учёту становятся сотрудниками, у проекта с
учётом времени — рабочие задачи, и за полгода — 150 записей табеля.
Повторяемо: сотрудник — по пользователю в компании, задача — по имени,
записи табеля — по ключу `coop_demo.tsw_<орг>_<n>`.
"""
import logging
import random
from datetime import date, timedelta

from . import load_sales as ls

_logger = logging.getLogger(__name__)

TASKS = [
    'Обследование объекта и замеры',
    'Проект электроснабжения, раздел ЭОМ',
    'Монтаж кабельных трасс',
    'Сборка и наладка щитов',
    'Монтаж вентиляции',
    'Пусконаладка автоматики',
    'Исполнительная документация',
    'Сдача объекта заказчику',
]
WORK = [
    'Выезд на объект', 'Согласование с заказчиком', 'Расчёт нагрузок',
    'Монтаж', 'Проверка и испытания', 'Подготовка чертежей',
    'Закупка материалов', 'Устранение замечаний', 'Планёрка',
]
LINES = 150


def load_showcase_timesheets(env, login='dashkevich'):
    if 'account.analytic.line' not in env or 'hr.employee' not in env:
        return 0
    showcase = ls._showcase(env, login)
    made = 0
    for org in showcase:
        company = org.coop_company_id
        project = env['project.project'].sudo().search(
            [('company_id', '=', company.id), ('allow_timesheets', '=', True)], limit=1)
        if not project:
            # Единственный такой проект витрины — в архиве: заводим рабочий.
            project = env['project.project'].sudo().with_company(company).create({
                'name': 'Электромонтаж складского комплекса «Северный»',
                'company_id': company.id, 'allow_timesheets': True,
                'partner_id': org.id,
            })
        users = env['coop.membership'].sudo().search([
            ('organization_id', '=', org.id), ('state', '=', 'active'),
        ]).partner_id.user_ids.filtered(lambda u: not u.share and company in u.company_ids)
        Employee = env['hr.employee'].sudo().with_company(company)
        employees = Employee.browse()
        for user in users:
            employees |= Employee.search([('user_id', '=', user.id), ('company_id', '=', company.id)], limit=1) \
                or Employee.create({'name': user.name, 'user_id': user.id, 'company_id': company.id})
        if not employees:
            continue
        Task = env['project.task'].sudo().with_company(company)
        tasks = Task.search([('project_id', '=', project.id)])
        for name in TASKS:
            if name not in tasks.mapped('name'):
                tasks |= Task.create({'name': name, 'project_id': project.id,
                                      'allocated_hours': random.Random(name).choice((16, 24, 40, 60, 80))})
        rnd = random.Random(20261129 + org.id)
        today = date.today()
        Line = env['account.analytic.line'].sudo().with_company(company)
        for number in range(LINES):
            xmlid = ls._key(env, 'tsw', org, number)
            if ls._have(env, xmlid):
                continue
            try:
                with env.cr.savepoint():
                    line = Line.create({
                        'project_id': project.id,
                        'task_id': tasks[rnd.randrange(len(tasks))].id,
                        'employee_id': employees[rnd.randrange(len(employees))].id,
                        'unit_amount': rnd.choice((0.5, 1, 1.5, 2, 3, 4, 6, 8)),
                        'date': today - timedelta(days=rnd.randint(0, 180)),
                        'name': rnd.choice(WORK),
                    })
                    ls._mark(env, xmlid, line)
                    made += 1
            except Exception as exc:  # noqa: BLE001
                _logger.warning('Табели витрины: запись %s не заведена: %s', xmlid, ls._flat(exc))
    _logger.info('Табели витрины: записей заведено %s', made)
    return made

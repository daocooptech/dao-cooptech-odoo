# -*- coding: utf-8 -*-
"""Заметки на штатных To-Do (задача 426).

У главного участника витрины (dashkevich) — три десятка заметок, у
демо-участников проектов — по две-четыре: свои мысли по проекту, списки
дел, памятки без проекта. Разброс: с проектом и без, со сроком и без,
выполненные и в архиве. Тексты — из набора по смыслу, к проекту
подставляется его название, поэтому копий одной строки нет.

Идемпотентно: у кого такие заметки уже есть (по названиям из набора) —
пропускается. Меток на заметках нет: платформа — как действующая.
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

PROJECT_NOTES = [
    ('Вопросы к инициатору — {p}', '<p>Уточнить срок окупаемости и кто ведёт учёт вкладов.</p>'),
    ('Что могу дать проекту «{p}»', '<ul><li>Транспорт на выходных</li><li>Опыт закупок</li></ul>'),
    ('Риски — {p}', '<p>Поставщик один, запасного нет. Спросить про страховку груза.</p>'),
    ('Созвон по «{p}»', '<p>Договорились: смета до пятницы, потом голосование по долям.</p>'),
    ('Посчитать долю в «{p}»', '<p>Вклад деньгами + часы. Сверить с экономической моделью проекта.</p>'),
    ('Документы для «{p}»', '<ul><li>Устав</li><li>Договор вклада</li><li>Акт передачи</li></ul>'),
    ('Идеи для «{p}»', '<p>Сделать предзаказ через складчину — снизит закупочную цену.</p>'),
    ('Кого позвать в «{p}»', '<p>Знакомый электрик из Твери, бухгалтер на аутсорсе.</p>'),
]
FREE_NOTES = [
    ('Список покупок на склад', '<ul><li>Паллетная плёнка</li><li>Стретч-худ</li><li>Маркировка</li></ul>'),
    ('Прочитать устав кооператива', '<p>Разделы про выход пайщика и распределение прибыли.</p>'),
    ('Позвонить в банк про счёт', '<p>Узнать тариф для кооператива и сроки открытия.</p>'),
    ('Мысли о вступлении в сообщество', '<p>Сначала посмотреть ленту месяц, потом решить.</p>'),
    ('Подготовить отчёт за месяц', '<p>Часы, вклады, закрытые сделки.</p>'),
    ('Обновить страницу «О себе»', '<p>Добавить опыт и навыки, фото работ.</p>'),
    ('Сверить расчёты по зачёту', '<p>Есть расхождение с контрагентом на 3 400 ₽.</p>'),
    ('Записаться на обучение', '<p>Курс по кооперативному учёту, начало в следующем месяце.</p>'),
]


def _notes_for(rnd, user, projects, count):
    today = date.today()
    vals = []
    for i in range(count):
        project = rnd.choice(projects) if projects and rnd.random() < 0.6 else False
        name, body = rnd.choice(PROJECT_NOTES if project else FREE_NOTES)
        deadline = today + timedelta(days=rnd.randint(-20, 40)) if rnd.random() < 0.45 else False
        vals.append({
            'name': name.format(p=project.name) if project else name,
            'description': body,
            'user_ids': [(6, 0, [user.id])],
            'project_id': False,
            'coop_project_id': project.id if project else False,
            'date_deadline': deadline,
            'priority': '1' if rnd.random() < 0.15 else '0',
            '_done': rnd.random() < 0.2,
            '_archived': rnd.random() < 0.06,
        })
    return vals


def load_project_notes(env):
    Task = env['project.task'].sudo().with_context(mail_create_nolog=True, tracking_disable=True)
    free_names = [name for name, _body in FREE_NOTES]
    prefixes = [name.split('{p}')[0] for name, _body in PROJECT_NOTES]
    rnd = random.Random(426)
    Project = env['coop.project'].sudo()
    users = env['res.users'].sudo().search([('share', '=', False), ('active', '=', True)])
    main = users.filtered(lambda u: u.login == 'dashkevich')
    created = 0
    for user in (main | users)[:60]:
        existing = Task.with_context(active_test=False).search([
            ('user_ids', 'in', user.ids), ('project_id', '=', False)]).mapped('name')
        if any(n in free_names or any(n.startswith(p) for p in prefixes) for n in existing):
            continue
        projects = Project.search([
            '|', ('partner_id', '=', user.partner_id.id),
            ('contribution_ids.partner_id', '=', user.partner_id.id)], limit=8)
        if not projects:
            projects = Project.search([], limit=5, offset=rnd.randint(0, 40))
        count = 30 if user == main else rnd.randint(2, 4)
        for vals in _notes_for(rnd, user, projects, count):
            done, archived = vals.pop('_done'), vals.pop('_archived')
            note = Task.with_user(user).sudo().create(vals)
            if done:
                note.state = '1_done'
            if archived:
                note.active = False
            created += 1
    _logger.info('Демо-заметки: добавлено %s', created)
    return created

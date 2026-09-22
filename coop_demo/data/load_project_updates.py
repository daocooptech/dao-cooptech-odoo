# -*- coding: utf-8 -*-
"""Отчёты о ходе запущенных проектов.

Пункт 14 разбора архитектора: ход проекта показывается штатным отчётом
`project.update`, а не собственной лентой новостей. Отчёт — документ:
заголовок, состояние, процент, дата, автор, описание; он уходит
подписчикам и виден в управлении проектами.

Здесь наполнение: без отчётов точка хода на карточке каталога была бы
серой у всех, и по ней нельзя было бы понять, работает ли она вообще.

Состояния берутся не наугад, а из того, в каком положении проект: у
завершённого отчёт «завершён», у замороженного «приостановлен», у
собравшего мало — «отстаёт». История пишется по нарастающей: первый
отчёт после запуска, дальше по ходу работ, и последний отражает
нынешнее положение дел.
"""
import logging
import random
from datetime import timedelta

from odoo import fields

_logger = logging.getLogger(__name__)

# Заголовок и описание по состоянию. Текст короткий и по делу: отчёт о
# ходе читают те, кто вложился, и вода в нём хуже молчания.
TEXTS = {
    'on_track': [
        ('Работы идут по плану',
         'Сделано то, что намечали на этот этап. Сроки держим, '
         'дополнительных вкладов не требуется.'),
        ('Первый этап закрыт',
         'Закупки прошли, подрядчик вышел на площадку. Следующий отчёт '
         'после приёмки работ этапа.'),
        ('Идём с небольшим опережением',
         'Часть работ удалось совместить, освободилось несколько дней. '
         'Запас оставляем на приёмку.'),
    ],
    'at_risk': [
        ('Появился риск по срокам',
         'Поставщик сдвинул отгрузку на две недели. Ищем замену, о '
         'решении сообщим отдельно. На смету это пока не влияет.'),
        ('Риск по смете',
         'Цены на материалы выросли против расчёта. Разницу пока '
         'покрываем из запаса, но если рост продолжится, вынесем вопрос '
         'на общее собрание.'),
    ],
    'off_track': [
        ('Отстаём от плана',
         'Работы встали из-за погоды и задержки материалов. Сроки '
         'пересматриваем, новый план вынесем на обсуждение.'),
        ('Сроки сорваны, разбираемся',
         'Подрядчик не вышел на объект. Готовим замену и считаем, во '
         'что обойдётся простой.'),
    ],
    'on_hold': [
        ('Работы приостановлены',
         'Проект заморожен решением инициаторов. Вклады сохранены, '
         'объявления сняты с публикации. Возобновим, когда снимется '
         'причина остановки.'),
    ],
    'done': [
        ('Проект завершён',
         'Работы приняты, результат передан. Остаётся распределение '
         'долей — оно идёт отдельным порядком.'),
    ],
}


def _state(project):
    """Каким должен быть последний отчёт у этого проекта.

    Выводится из положения дел, а не назначается наугад: отчёт «идёт по
    плану» у замороженного проекта — ложь, которую видно сразу.
    """
    if project.state == 'done':
        return 'done'
    if project.state == 'frozen':
        return 'on_hold'
    if project.state in ('cancelled', 'failed'):
        return 'off_track'
    # Запущенный. Смотрим на то, что о нём известно, а не бросаем
    # жребий: отчёт «есть риск» у проекта, который идёт как надо, —
    # такая же ложь, как «по плану» у замороженного.
    if project.project_id.stage_id.name == 'Остановлен':
        return 'on_hold'
    # Срок сбора вышел, а проект всё ещё в работе: значит, работы идут
    # дольше, чем на них отводили. Это и есть риск по срокам.
    if project.date_deadline and project.date_deadline < fields.Date.today():
        return 'at_risk'
    if project.readiness >= 100:
        return 'on_track'
    if project.readiness >= 70:
        return 'at_risk'
    return 'off_track'


def load_project_updates(env):
    if 'project.update' not in env:
        _logger.info('Отчёты о ходе: модуля проектов нет, пропускаю')
        return 0

    Report = env['project.update'].sudo()
    projects = env['coop.project'].sudo().search([
        ('project_id', '!=', False),
        ('state', 'in', ('running', 'done', 'frozen', 'cancelled')),
    ], order='id')
    projects = projects.filtered(
        lambda p: not Report.search_count([('project_id', '=', p.project_id.id)]))
    if not projects:
        _logger.info('Отчёты о ходе: все проекты наполнены, пропускаю')
        return 0

    rnd = random.Random(20260915)
    today = fields.Date.today()
    built = 0
    for project in projects:
        total = _state(project)
        # История: от одного до трёх отчётов, последний — нынешнее
        # положение. Промежуточные всегда «по плану»: если бы дела шли
        # плохо с самого начала, проект бы не дожил до запуска.
        how_many = rnd.randint(1, 3)
        start = project.date_start or (today - timedelta(days=90))
        for step in range(how_many):
            last_one = step == how_many - 1
            state = total if last_one else 'on_track'
            heading, description = rnd.choice(TEXTS[state])
            share = int(round((step + 1) * 100.0 / how_many))
            date_value = start + timedelta(days=int(30 * step) + rnd.randint(1, 20))
            if date_value > today:
                date_value = today
            Report.create({
                'name': heading,
                'project_id': project.project_id.id,
                'status': state,
                'progress': 100 if state == 'done' else min(share, 95),
                'date': date_value,
                # Автор — тот, кто проект затеял, если у него есть
                # учётная запись. У большинства демо-участников её нет:
                # они карточки, а не пользователи, — и тогда автором
                # становится администратор узла.
                'user_id': (project.partner_id.user_ids[:1].id
                            or env.ref('base.user_admin').id),
                'description': '<p>%s</p>' % description,
            })
            built += 1
    _logger.info('Отчёты о ходе: создано %s на %s проектов',
                 built, len(projects))
    return built

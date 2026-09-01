# -*- coding: utf-8 -*-
"""Задачи рабочей группы, менеджер сообщества и токены на балансах.

Задачи взяты не с потолка: это то, что действительно нужно проекту на
нынешнем этапе — перенос разделов, правовой разбор, переводы, тексты.
Демонстрационный раздел «Помощь проекту» на выдуманных задачах выглядел бы
пустым обещанием, а на настоящих по нему сразу видно, чем помочь.

Токены раздаются части участников, чтобы работало продвижение: объявление
без баланса продвинуть нельзя, и раздел «Ресурсы» показывал бы кнопку,
которая всегда отказывает.
"""
import logging

from odoo import fields

_logger = logging.getLogger(__name__)

# Состояния задач разведены намеренно: на экране должны быть видны все
# стадии, а не только «опубликовано». По одному состоянию не понять, как
# устроен путь от заявки до приёмки.
TASKS = [
    ('Перенести раздел «Навыки» из макета на движок',
     'Каталог навыков: модель, карточка, поиск и наполнение из '
     '<code>skills.html</code> прототипа. Готово, когда раздел открывается '
     'в меню и содержит те же навыки, что в макете.',
     'Программирование, Разработка', 120, 'published'),
    ('Разобрать правовой статус токенов платформы по 282-ФЗ',
     'Закон вступает в силу 01.09.2026. Нужно заключение: не меняет ли он '
     'квалификацию внутренней единицы платформы, которой оплачивается '
     'продвижение. Готово, когда есть письменный разбор со ссылками на нормы.',
     'Юрисконсульт', 200, 'published'),
    ('Вычитать тексты интерфейса каталога организаций',
     'Проверить формулировки на экранах: подсказки полей, пустые состояния, '
     'сообщения об ошибках. Готово, когда правки внесены и вычитаны повторно.',
     'Переводчик', 60, 'published'),
    ('Собрать список кооперативов Дербента и окрестностей',
     'Открытые источники: реестры, сайты, местная пресса. Нужны название, '
     'форма, город, чем занимаются. Готово, когда список сверен и оформлен '
     'таблицей.', 'Аналитика, Data Science', 80, 'published'),
    ('Нарисовать иллюстрации для раздела «Проекты»',
     'Четыре иллюстрации в стиле платформы: сбор вскладчину, распределение '
     'долей, общее собрание, приёмка работ. Готово, когда файлы приняты в '
     'исходниках.', 'Дизайн, графика', 150, 'published'),
    ('Проверить каталог ресурсов на мобильном',
     'Пройти каталог и карточку ресурса на телефоне, записать всё, что '
     'ломается или нечитаемо. Готово, когда список замечаний передан со '
     'снимками экрана.', 'Веб-дизайн', 50, 'assigned'),
    ('Описать порядок приёма в кооператив для справки платформы',
     'Пошагово: заявление, решение общего собрания, паевой взнос, запись в '
     'реестре. Со ссылками на закон 3085-1. Готово, когда текст согласован '
     'с юристом.', 'Юрисконсульт', 90, 'submitted'),
    ('Перевести описание платформы на английский',
     'Лендинг и раздел «На чём мы стоим». Не подстрочник: текст должен '
     'читаться носителем. Готово, когда перевод вычитан.',
     'Переводчик', 110, 'accepted'),
]


def grant_admin_roles(env):
    """Выдать администратору стенда все роли платформы.

    Решение владельца 137. Через XML это не работает: запись
    `base.user_admin` объявлена в базовом модуле с защитой от обновления,
    и наше переопределение загрузчик молча пропускает — ровно как было со
    знаком рубля и с reference-данными. На стенде это выглядело так:
    роли в файле есть, а администратор не может завести движение токенов.

    Само правило «платформа не сторона отношений участников» это не
    нарушает: сквозное правило доступа к членству живёт в этом же
    демонстрационном модуле, и на узле без него строгая модель остаётся.
    """
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if not admin:
        return
    groups = [env.ref(xmlid, raise_if_not_found=False) for xmlid in (
        'coop_base.group_coop_platform',
        'coop_base.group_coop_member',
        'coop_base.group_coop_board',
        'coop_base.group_coop_audit',
        'coop_bounty.group_coop_community_manager',
    )]
    missing = [g for g in groups if g and g not in admin.group_ids]
    if missing:
        admin.sudo().write({'group_ids': [(4, g.id) for g in missing]})
        _logger.info('Администратору выданы роли: %s',
                     ', '.join(g.name for g in missing))


def load_bounty(env):
    # Через sudo: загрузчик вызывается при обновлении модуля, и права
    # текущего пользователя к демонстрационным данным отношения не
    # имеют — он их не создаёт, а получает вместе с модулем.
    Task = env['coop.bounty.task'].sudo()
    Partner = env['res.partner'].sudo()
    manager_group = env.ref('coop_bounty.group_coop_community_manager')

    # Менеджер сообщества — отдельная учётная запись рабочей группы. Роль
    # платформы, а не кооператива: прав в чужих кооперативах она не даёт.
    manager = env['res.users'].sudo().search([('login', '=', 'community')], limit=1)
    if not manager:
        manager = env['res.users'].sudo().create({
            'name': 'Тихонова Ольга Сергеевна',
            'login': 'community',
            'password': 'community',
            'group_ids': [(4, env.ref('base.group_user').id),
                          (4, manager_group.id),
                          (4, env.ref('coop_base.group_coop_platform').id)],
            'lang': 'ru_RU',
            'tz': 'Europe/Moscow',
        })
        manager.partner_id.write({'city': 'Москва', 'coop_is_participant': False})
    elif manager_group not in manager.group_ids:
        manager.write({'group_ids': [(4, manager_group.id)]})

    specializations = {s.name: s for s in env['coop.specialization'].sudo().search([])}
    # Исполнители берутся из каталога людей: задачу берёт участник, а не
    # абстрактный пользователь.
    people = Partner.search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id', limit=8)

    created = 0
    for index, (name, description, specialization, reward, state) in enumerate(TASKS):
        task = Task.search([('name', '=', name)], limit=1)
        values = {
            'name': name,
            'description': '<p>%s</p>' % description,
            'reward_tokens': reward,
            'coop_specialization_id': specializations.get(specialization).id
                                      if specializations.get(specialization) else False,
            'manager_id': manager.id,
            'deadline': fields.Date.add(fields.Date.context_today(Task),
                                        days=14 + index * 7),
        }
        if task:
            # Состояние у существующей задачи не трогаем: её могли двигать
            # руками, показывая раздел, и откат этого при обновлении
            # модуля выглядел бы как потеря работы.
            task.write({k: v for k, v in values.items() if k != 'state'})
            continue

        task = Task.create(dict(values, state='draft'))
        created += 1

        if state == 'published':
            task.action_publish()
            continue

        # Задачи в работе и дальше: заявка, утверждение, сдача, приёмка —
        # проходятся теми же действиями, что и в жизни, а не проставлением
        # состояния. Иначе демо-данные разойдутся с логикой: у принятой
        # задачи не окажется ни исполнителя, ни начисленных токенов.
        task.action_publish()
        if not people:
            continue
        performer = people[index % len(people)]
        application = env['coop.bounty.application'].sudo().create({
            'task_id': task.id,
            'partner_id': performer.id,
            'message': 'Возьмусь, делал похожее.',
        })
        application.action_approve()

        if state in ('submitted', 'accepted'):
            task.write({'state': 'submitted'})
        if state == 'accepted':
            task.action_accept()

    # Токены на балансы: без них продвижение объявления невозможно, и
    # кнопка в каталоге ресурсов всегда отказывала бы.
    Token = env['coop.token.transaction'].sudo()
    owners = Partner.search([('coop_is_participant', '=', True)], order='id', limit=40)
    topped = 0
    for index, partner in enumerate(owners):
        if partner.coop_token_balance:
            continue
        Token.create({
            'partner_id': partner.id,
            'amount': 200 + (index % 5) * 150,
            'kind': 'topup',
            'description': 'Пополнение баланса',
        })
        topped += 1

    _logger.info('Помощь проекту: задач создано %s, балансов пополнено %s',
                 created, topped)

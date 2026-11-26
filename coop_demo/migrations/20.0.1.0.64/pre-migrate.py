# -*- coding: utf-8 -*-
"""№ 341, решение 510: подрядные вакансии — в задачи с результатом.

Идёт до загрузки данных модуля: загрузчик демо перезаписывает вакансии,
и подрядные ДАО упёрлись бы в новый запрет. Миграция coop_vacancies запомнила подрядные вакансии (таблица
coop_vacancy_to_task_510). Каждая становится задачей от той же
организации: описание, проект, город, специализация, снимок и галерея,
критерии приёмки. Сумма — верх вилки за результат (за месяц, смену, час —
пересчёт на объём результата); рубли — способом «₽», остаток в пай — ещё
и долей в проекте, токены ДАО — токенами проекта. Отклики — заявками:
приглашённый — утверждён, отклонённый — отклонён. Состояние: черновик —
черновик; открытая — опубликована, а с приглашённым — в работе; закрытая —
принята у приглашённого, без него — отменена. Ссылки на вакансию
(избранное, уведомления, переписка, галерея) переходят на задачу, затем
вакансия удаляется.
"""
import json
import logging
import random
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)

# Объём результата в единицах периода оплаты.
PERIOD_UNITS = {'month': 1, 'job': 1, 'shift': 5, 'hour': 40, 'lesson': 8}

CRITERIA = [
    'Результат сдан в оговорённый срок',
    'Объём соответствует описанию задачи',
    'Замечания заказчика устранены до приёмки',
    'Приложены фото или файлы результата',
    'Использованы материалы, согласованные с заказчиком',
    'Место работ убрано, остатки материалов переданы',
    'Сдана короткая инструкция, как пользоваться результатом',
    'Результат проверен вторым участником проекта',
]
NOTE = ('Перенесено из вакансии: работа с результатом — задачей с приёмкой, '
        'подряда в вакансиях нет (решение 510). Отклики стали заявками.')
APP_STATES = {'applied': 'applied', 'invited': 'approved', 'declined': 'rejected'}
GENERIC_TABLES = ('coop_favorite', 'coop_media', 'coop_notification',
                  'coop_document', 'mail_activity', 'mail_followers')


def _amount(vacancy):
    top = vacancy.pay_to or vacancy.pay_from or 0
    if not top:
        return 0
    return max(int(round(top * PERIOD_UNITS.get(vacancy.pay_period, 1), -2)), 1000)


def _manager(env, payer, cache):
    """Кто размещает задачу от организации: её участник с входом, иначе
    тот, кто уже размещал её задачи, иначе — самый частый размещающий."""
    if payer.id not in cache:
        Task = env['coop.bounty.task'].sudo()
        users = env['coop.membership'].sudo().search([
            ('organization_id', '=', payer.id), ('state', '=', 'active'),
        ]).partner_id.user_ids.filtered(lambda u: not u.share)
        if not users:
            users = Task.search([('payer_id', '=', payer.id),
                                 ('manager_id.login', '!=', '__system__')],
                                limit=1).manager_id
        if not users:
            if 'any' not in cache:
                rows = Task._read_group([('manager_id.share', '=', False)],
                                        ['manager_id'], ['__count'],
                                        order='__count desc', limit=2)
                cache['any'] = next((u for u, _n in rows if u.id != SUPERUSER_ID
                                     and u.login != '__system__'), Task.manager_id[:0])
            users = cache['any']
        cache[payer.id] = users[:1]
    return cache[payer.id]


def migrate(cr, version):
    cr.execute("SELECT to_regclass('coop_vacancy_to_task_510')")
    if not cr.fetchone()[0]:
        return
    cr.execute('SELECT vacancy_id, pay_method FROM coop_vacancy_to_task_510 ORDER BY vacancy_id')
    rows = cr.fetchall()
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True,
                                             'mail_create_nolog': True,
                                             'mail_notrack': True})
    rnd = random.Random(20261126510)
    today = fields.Date.context_today(env['coop.bounty.task'])
    Vacancy = env['coop.vacancy'].sudo()
    Task = env['coop.bounty.task'].sudo()
    TaskApp = env['coop.bounty.application'].sudo()
    CoopProject = env['coop.project'].sudo().with_context(active_test=False)
    method = {code: env.ref('coop_bounty.method_%s' % code)
              for code in ('rub', 'share', 'project_tokens')}
    moved = {}
    keys = []
    managers = {}
    for vacancy_id, pay in rows:
        vacancy = Vacancy.browse(vacancy_id).exists()
        if not vacancy or not vacancy.partner_id:
            continue
        # У вакансии — проект в управлении, у задачи — карточка проекта.
        project = CoopProject.search([('project_id', '=', vacancy.project_id.id)],
                                     limit=1) if vacancy.project_id else CoopProject
        methods = method['project_tokens'] if pay == 'tokens' else method['rub']
        if pay == 'rub_share' and project:
            methods |= method['share']
        apps = vacancy.application_ids.sorted('id')
        invited = apps.filtered(lambda a: a.state == 'invited')[:1]
        if vacancy.state == 'draft':
            state = 'draft'
        elif vacancy.state == 'published':
            state = 'assigned' if invited else 'published'
        else:
            state = 'accepted' if invited else 'cancelled'
        created = fields.Date.to_date(vacancy.create_date) or today
        values = {
            'name': vacancy.name,
            'description': vacancy.description,
            'payer_id': vacancy.partner_id.id,
            'project_id': project.id or False,
            'reward_tokens': _amount(vacancy),
            'allowed_method_ids': [(6, 0, methods.ids)],
            'share_percent': vacancy.share_percent if 'share' in methods.mapped('code') else 0,
            'coop_specialization_id': vacancy.coop_specialization_id.id or False,
            'city': vacancy.city,
            # Открытой задаче — срок впереди, закрытой — от её начала.
            'deadline': (today + timedelta(days=rnd.randint(10, 60))
                         if state in ('draft', 'published')
                         else created + timedelta(days=rnd.randint(14, 75))),
            'state': state,
            'criterion_ids': [(0, 0, {'sequence': i, 'name': name,
                                      'done': state == 'accepted'})
                              for i, name in enumerate(
                                  rnd.sample(CRITERIA, rnd.randint(2, 4)))],
        }
        manager = (vacancy.author_id.user_ids[:1]
                   or _manager(env, vacancy.partner_id, managers))
        if manager:
            values['manager_id'] = manager.id
        if vacancy.image_1920:
            values['image_1920'] = vacancy.image_1920
        if invited:
            assigned = created + timedelta(days=rnd.randint(2, 9))
            values.update({
                'assignee_id': invited.partner_id.id,
                'payment_mode': methods[:1].code,
                'assigned_on': assigned,
            })
            if state == 'accepted':
                submitted = assigned + timedelta(days=rnd.randint(5, 30))
                values.update({
                    'submitted_on': submitted,
                    'accepted_on': submitted + timedelta(days=rnd.randint(0, 4)),
                })
        task = Task.create(values)
        task.message_post(body=NOTE, message_type='notification',
                          subtype_xmlid='mail.mt_note')
        for app in apps:
            TaskApp.create({
                'task_id': task.id,
                'partner_id': app.partner_id.id,
                'message': app.message,
                'method_id': methods[:1].id,
                'state': APP_STATES.get(app.state, 'applied'),
            })
        cr.execute('UPDATE coop_bounty_task SET create_date = %s WHERE id = %s',
                   (vacancy.create_date, task.id))
        moved[vacancy.id] = task.id
        if vacancy.import_key:
            keys.append(vacancy.import_key)

    env.flush_all()
    for old, new in moved.items():
        # У задачи уже есть подписчики (автор) — совпадающих убираем.
        cr.execute("""
            DELETE FROM mail_followers
             WHERE res_model = 'coop.vacancy' AND res_id = %s
               AND partner_id IN (SELECT partner_id FROM mail_followers
                                   WHERE res_model = 'coop.bounty.task' AND res_id = %s)""",
                   (old, new))
        for table in GENERIC_TABLES:
            cr.execute('UPDATE %s SET res_model = %%s, res_id = %%s '
                       "WHERE res_model = 'coop.vacancy' AND res_id = %%s" % table,
                       ('coop.bounty.task', new, old))
        cr.execute("UPDATE mail_message SET model = 'coop.bounty.task', res_id = %s "
                   "WHERE model = 'coop.vacancy' AND res_id = %s", (new, old))
        cr.execute("UPDATE ir_attachment SET res_model = 'coop.bounty.task', res_id = %s "
                   "WHERE res_model = 'coop.vacancy' AND res_id = %s AND res_field IS NULL",
                   (new, old))
    env.invalidate_all()
    Vacancy.browse(list(moved)).unlink()
    # Задачи проектов блокируют токены проекта — выделенного должно хватать.
    Task.browse(list(moved.values())).project_id._coop_bounty_fit_limit()
    Param = env['ir.config_parameter'].sudo()
    keys += json.loads(Param.get_str('coop_demo.vacancies_moved_to_tasks_510') or '[]')
    Param.set_str('coop_demo.vacancies_moved_to_tasks_510', json.dumps(sorted(set(keys))))
    cr.execute('DROP TABLE coop_vacancy_to_task_510')
    _logger.info('Решение 510: подрядных вакансий перенесено в задачи — %s', len(moved))

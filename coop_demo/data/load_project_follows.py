# -*- coding: utf-8 -*-
"""Подписки на проекты — чтобы лента подписок была не пустой.

Лента подписок (решения 40, 42 и 43) показывает новости только тех
проектов, на которые человек подписан. На боевой 24 сентября 2026 таких
подписок не было ни одной, и лента была бы пустой у всех — ровно тот
случай, когда по разделу нельзя понять, работает ли он вообще.

Подписка — штатный подписчик записи (`mail.followers`), как и у страниц
участников (`load_biography.add_followers`). Не наугад, а по делу:

* инициатор проекта подписан на свой проект;
* вкладчик подписан на проекты, куда вложился, — кроме отклонённых,
  отозванных и истёкших вкладов;
* главный участник витрины — ещё и на все проекты с новостями, где
  он не участвует: лента под его учётной записью — та, которую открывают
  первой.

Повторный запуск ничего не удваивает: существующие пары «проект —
человек» пропускаются.
"""
import logging

_logger = logging.getLogger(__name__)

GONE = ('declined', 'expired', 'withdrawn')


def load_project_follows(env, login='dashkevich'):
    if 'coop.project' not in env:
        return 0
    Project = env['coop.project'].sudo()
    Follower = env['mail.followers'].sudo()
    projects = Project.search([])
    if not projects:
        return 0

    existing = {(f.res_id, f.partner_id.id)
                for f in Follower.search([('res_model', '=', 'coop.project')])}
    rows = []

    def add(project_id, partner_id):
        key = (project_id, partner_id)
        if partner_id and key not in existing:
            existing.add(key)
            rows.append({'res_model': 'coop.project', 'res_id': project_id,
                         'partner_id': partner_id})

    for project in projects:
        add(project.id, project.partner_id.id)

    for contribution in env['coop.project.contribution'].sudo().search(
            [('state', 'not in', GONE)]):
        add(contribution.project_id.id, contribution.partner_id.id)

    showcase = env['res.users'].sudo().search(
        [('login', '=', login)], limit=1).partner_id
    if showcase:
        with_news = projects.filtered(
            lambda p: p.project_id and p.project_id.update_ids)
        # На все проекты с новостями: лента под его учётной записью —
        # та, которую открывают первой, и в ней должно быть видно и
        # отбор, и листание. Дюжины проектов на это не хватало.
        for project_id in with_news.ids:
            add(project_id, showcase.id)

    if rows:
        Follower.create(rows)
    _logger.info('Подписки на проекты: добавлено %s', len(rows))
    return len(rows)

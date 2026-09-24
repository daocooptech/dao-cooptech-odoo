# -*- coding: utf-8 -*-
"""Лента подписок — новости проектов, на которые человек подписан.

Решения 40, 42 и 43 журнала владельца (13 августа 2026), исполненные
только в дизайн-макете: общая лента показывает новости проектов, на
которые человек подписан, одной хронологической лентой, а сбоку —
отбор по нескольким проектам сразу и по диапазону дат.

Новость проекта на движке — штатный отчёт о ходе (`project.update`):
так решено разбором архитектора (пункт 14), и загрузчик демо-данных
наполняет именно их. Подписка — штатный подписчик проекта платформы
(`coop.project`, кнопка «Подписаться»). Своей модели у ленты нет, она
лишь собирает одно с другим. Отбор — та же боковая панель, что у
каталогов (`coop.catalog.catalog_filters`).
"""
from odoo import _, api, models


class CoopProjectFeed(models.Model):
    _inherit = 'coop.project'

    @api.model
    def _coop_feed_followed(self):
        """Проекты платформы, на которые подписан текущий человек."""
        partner = self.env.user.partner_id
        ids = self.env['mail.followers'].sudo().search([
            ('partner_id', '=', partner.id),
            ('res_model', '=', 'coop.project'),
        ]).mapped('res_id')
        # Только те, что человеку можно читать: подписка переживает смену
        # состояния проекта, и среди подписанных бывают уже скрытые от
        # него — лента падала на них «Ошибкой доступа».
        return self.browse(ids).exists()._filtered_access('read')

    @api.model
    def action_coop_project_feed(self):
        """Открыть ленту подписок на проекты.

        Серверным действием, а не окном с готовым отбором: подписки у
        каждого свои и меняются, а отбор окна записывается один раз, при
        установке модуля.
        """
        managed = self._coop_feed_followed().mapped('project_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Лента'),
            'res_model': 'project.update',
            'view_mode': 'kanban',
            'views': [(self.env.ref('coop_messages.view_coop_feed_kanban').id,
                       'kanban')],
            'search_view_id': [self.env.ref(
                'coop_messages.view_coop_feed_search').id],
            'domain': [('project_id', 'in', managed.ids)],
            'context': {'create': False},
            'target': 'current',
        }


class ProjectUpdate(models.Model):
    _inherit = 'project.update'

    @api.model
    def _coop_catalog_filters(self, domain):
        """Панель отбора ленты: проекты — несколько сразу — и даты."""
        followed = self.env['coop.project']._coop_feed_followed()
        options = [{'value': p.project_id.id, 'label': p.name}
                   for p in followed.sorted('name') if p.project_id]
        return [
            {'code': 'project_id', 'label': 'Проекты',
             'hint': 'Проекты, на которые вы подписаны. Можно отметить '
                     'несколько — покажутся новости любого из них.',
             'widget': 'multi', 'field': 'project_id',
             'empty': 'Вы пока ни на один проект не подписаны',
             'options': options},
            {'code': 'date', 'label': 'Даты',
             'hint': 'С какого и по какой день. Пустое поле — без '
                     'ограничения.',
             'widget': 'daterange', 'field': 'date'},
        ]

    def action_coop_feed_open(self):
        """Щелчок по новости ведёт на страницу проекта платформы, а не в
        служебную форму отчёта: ленту читают ради проекта."""
        self.ensure_one()
        project = self.env['coop.project'].search(
            [('project_id', '=', self.project_id.id)], limit=1)
        if project:
            return project.action_coop_open_page()
        return False


class ResPartnerFeed(models.Model):
    """Ленты подписок на людей и на организации — решение 65.

    Решение от 13 августа: у каждого каталога — проектов, организаций и
    людей — своя лента подписок. Новость человека или организации — запись
    на стене их страницы, то есть в обсуждении контакта (стена — это
    обсуждение, `WALL_MODELS` в `coop_theme/static/src/js/wall.js`).
    Подписка — штатный подписчик контакта, как у проектов.
    """
    _inherit = 'res.partner'

    @api.model
    def _coop_feed_followed_pages(self, companies):
        partner = self.env.user.partner_id
        ids = self.env['mail.followers'].sudo().search([
            ('partner_id', '=', partner.id),
            ('res_model', '=', 'res.partner'),
        ]).mapped('res_id')
        pages = self.browse(ids).exists()._filtered_access('read')
        return pages.filtered(lambda p: bool(p.is_company) == companies)

    @api.model
    def _coop_wall_feed(self, companies):
        pages = self._coop_feed_followed_pages(companies)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Лента'),
            'res_model': 'mail.message',
            'view_mode': 'kanban',
            'views': [(self.env.ref('coop_messages.view_coop_wall_feed_kanban').id,
                       'kanban')],
            'search_view_id': [self.env.ref(
                'coop_messages.view_coop_wall_feed_search').id],
            # Только то, что написали люди: смена полей, приглашения и
            # прочий служебный журнал в ленте новостей — шум.
            'domain': [('model', '=', 'res.partner'),
                       ('res_id', 'in', pages.ids),
                       ('message_type', '=', 'comment')],
            'context': {'create': False},
            'target': 'current',
        }

    @api.model
    def action_coop_people_feed(self):
        return self._coop_wall_feed(companies=False)

    @api.model
    def action_coop_orgs_feed(self):
        return self._coop_wall_feed(companies=True)


class MailMessageFeed(models.Model):
    _inherit = 'mail.message'

    @api.model
    def _coop_catalog_filters(self, domain):
        """Панель отбора ленты стен: чьи стены — несколько сразу — и даты.

        Из чего выбирать, берётся из основного отбора раздела (его
        передаёт панель в контексте, `coop_base_domain`): в ленте людей —
        люди, в ленте организаций — организации, на которых человек
        подписан.
        """
        base = self.env.context.get('coop_base_domain') or []
        model, ids = None, []
        for leaf in base:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3:
                if leaf[0] == 'model' and leaf[1] == '=':
                    model = leaf[2]
                elif leaf[0] == 'res_id' and leaf[1] == 'in':
                    ids = list(leaf[2])
        if model != 'res.partner':
            return []
        pages = self.env['res.partner'].browse(ids).exists()._filtered_access('read')
        companies = pages[:1].is_company
        return [
            {'code': 'res_id',
             'label': (('Организации' if companies else 'Люди')
                       if pages else 'Подписки'),
             'hint': 'На кого вы подписаны. Можно отметить нескольких — '
                     'покажутся записи любого из них.',
             'widget': 'multi', 'field': 'res_id',
             'empty': 'Вы пока ни на кого не подписаны',
             'options': [{'value': p.id, 'label': p.name}
                         for p in pages.sorted('name')]},
            {'code': 'date', 'label': 'Даты',
             'hint': 'С какого и по какой день. Пустое поле — без '
                     'ограничения.',
             'widget': 'daterange', 'field': 'date', 'datetime': True},
        ]

    def action_coop_feed_open(self):
        """Щелчок по записи ведёт на страницу того, чья это стена."""
        self.ensure_one()
        record = self.env[self.model].browse(self.res_id).exists()
        if record and hasattr(record, 'action_coop_open_page'):
            return record.action_coop_open_page()
        return False

# -*- coding: utf-8 -*-
"""Запись из каталогов, прикреплённая к посту стены (№ 454).

Владелец 15.11.2026: «возможность прикрепить к ленте (в том числе в
управлении проектом) задачу или ресурс или мероприятие и т. д., что
уместно из наших каталогов». Образец — холст ленты, доска «№ 454 ·
Прикрепить запись из каталогов» (26.11).

К посту — одна запись. Что уместно, решает стена: у проекта — его задачи,
ресурсы сметы, сделки и мероприятия инициатора; у человека и организации —
их объявления, сделки, мероприятия и документы; у сообщества — его
мероприятия. Искать и прикреплять — только то, что видно автору; карточку
каждый видит по своим правам, кому запись закрыта — «запись вам не видна».
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .coop_wall_comment import WALL_MODELS

ICONS = {
    'task': 'checklist',
    'need': 'inventory_2',
    'resource': 'inventory_2',
    'event': 'event',
    'deal': 'handshake',
    'doc': 'description',
}


def _project_tasks(page):
    return ['|', ('project_id', '=', page.project_id.id or 0),
            ('coop_project_id', '=', page.id)]


def _parties(page):
    return ['|', ('party_a_id', '=', page.id), ('party_b_id', '=', page.id)]


# Стена → [(вид, подпись, модель, домен от страницы)]. Порядок — порядок
# отборов в окне выбора.
SOURCES = {
    'coop.project': [
        ('task', 'Задачи', 'project.task', _project_tasks),
        ('need', 'Ресурсы сметы', 'coop.resource',
         lambda p: [('project_id', '=', p.id)]),
        ('event', 'Мероприятия', 'coop.event',
         lambda p: [('organizer_id', '=', p.partner_id.id)]),
        ('deal', 'Сделки', 'coop.deal', lambda p: [('project_id', '=', p.id)]),
    ],
    'res.partner': [
        ('resource', 'Объявления', 'coop.resource',
         lambda p: [('owner_id', '=', p.id)]),
        ('deal', 'Сделки', 'coop.deal', _parties),
        ('event', 'Мероприятия', 'coop.event',
         lambda p: [('organizer_id', '=', p.id)]),
        ('doc', 'Документы', 'coop.document', _parties),
    ],
    'coop.community': [
        ('event', 'Мероприятия', 'coop.event',
         lambda p: [('community_id', '=', p.id)]),
    ],
}

# Что ставить справа в карточке — первое заполненное.
SIDE_DATES = ('date_deadline', 'date_start', 'date')


class MailMessage(models.Model):
    _inherit = 'mail.message'

    coop_rec_model = fields.Char(string='Прикреплённая запись: модель')
    coop_rec_id = fields.Integer(string='Прикреплённая запись: номер')

    def _store_message_fields(self, res, **kwargs):
        super()._store_message_fields(res, **kwargs)
        res.attr('coop_rec', lambda m: m._coop_rec_data())

    # ── Что уместно на этой стене ───────────────────────────────────

    @api.model
    def _coop_attach_sources(self, model, res_id):
        """[(вид, подпись, модель, домен)] — только каталоги, что стоят."""
        if model not in WALL_MODELS:
            return []
        page = self.env[model].sudo().browse(res_id).exists()
        if not page:
            return []
        return [(kind, label, target, domain(page))
                for kind, label, target, domain in SOURCES.get(model, [])
                if target in self.env]

    @api.model
    def coop_attach_kinds(self, model, res_id):
        return [{'id': kind, 'label': label}
                for kind, label, _t, _d in self._coop_attach_sources(model, res_id)]

    @api.model
    def coop_attach_search(self, model, res_id, kind=False, query='', limit=20):
        """Записи, которые автор может прикрепить. Без sudo: только видимое."""
        found = []
        for k, label, target, domain in self._coop_attach_sources(model, res_id):
            if kind and kind != 'all' and kind != k:
                continue
            Model = self.env[target]
            dom = list(domain)
            if query:
                dom += [(Model._rec_name or 'display_name', 'ilike', query)]
            records = Model.search(dom, limit=limit, order='id desc')
            found += [self._coop_rec_card(r, k, label) for r in records]
        return found[:limit] if kind in (False, 'all') else found

    @api.model
    def coop_attach_set(self, message_id, rec_model, rec_id):
        """Прикрепить запись к только что опубликованному посту."""
        message = self.browse(message_id).exists()
        me = self.env.user.partner_id
        if (not message or message.model not in WALL_MODELS
                or message.author_id != me):
            raise UserError(_("Прикрепить можно только к своей записи."))
        for _k, _l, target, domain in self._coop_attach_sources(
                message.model, message.res_id):
            if target == rec_model and self.env[target].search_count(
                    domain + [('id', '=', rec_id)], limit=1):
                message.sudo().write({'coop_rec_model': rec_model,
                                      'coop_rec_id': rec_id})
                return self.browse(message_id)._coop_rec_data()
        raise UserError(_("Эту запись к этой ленте прикрепить нельзя."))

    # ── Карточка ───────────────────────────────────────────────────

    def _coop_rec_data(self):
        """Карточка прикреплённой записи глазами смотрящего — или False."""
        self.ensure_one()
        message = self.sudo()
        if not message.coop_rec_model or message.coop_rec_model not in self.env:
            return False
        # Проверка — от имени смотрящего, как у репоста: данные для
        # браузера движок собирает и под суперпользователем.
        record = self.env[message.coop_rec_model].sudo(False).browse(
            message.coop_rec_id).exists()
        if not record or not record._filtered_access('read'):
            return {'hidden': True}
        kind, label = 'doc', ''
        for k, lab, target, _d in SOURCES.get(message.model, []):
            if target == message.coop_rec_model:
                kind, label = k, lab
                break
        return self._coop_rec_card(record, kind, label)

    @api.model
    def _coop_rec_card(self, record, kind, label):
        meta = [record._description or label]
        state = record._fields.get('state')
        if state is not None and state.type == 'selection' and record.state:
            meta.append(dict(state._description_selection(self.env)).get(
                record.state, ''))
        side = ''
        for name in SIDE_DATES:
            field = record._fields.get(name)
            if field is not None and field.type in ('date', 'datetime') and record[name]:
                value = record[name]
                if field.type == 'datetime':
                    value = fields.Datetime.context_timestamp(record, value)
                side = value.strftime('%d.%m.%Y')
                break
        return {
            'model': record._name,
            'id': record.id,
            'kind': kind,
            'icon': ICONS.get(kind, 'link'),
            'title': record.display_name or '',
            'meta': ' · '.join(m for m in meta if m),
            'side': side,
            'url': '/odoo/%s/%s' % (record._name, record.id),
        }

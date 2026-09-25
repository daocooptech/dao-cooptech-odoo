# -*- coding: utf-8 -*-
"""Страница «Избранное» — всё отмеченное одним экраном, вкладками по видам.

Решение 408 (24 сентября 2026): сердечки и вкладка «Избранное» в каждом
каталоге — как в макете, — и сверх макета общая страница со вкладками по
типу содержимого и значок в шапке. Хранилище одно — `coop.favorite`;
записи со стен — звёздочка движка под записью (`starred_partner_ids`).

Здесь только чтение и открытие: схему хранилища (`coop_base`) не трогаем.
"""
import re

from odoo import api, fields, models

WALL_MODELS = ('res.partner', 'coop.project', 'coop.community')

# Порядок вкладок и их имена. Модели, которых нет на узле (модуль не
# поставлен), пропускаются; незнакомые — встают в конец под своим именем.
KINDS = [
    ('people', 'res.partner', 'Люди'),
    ('orgs', 'res.partner', 'Организации'),
    ('projects', 'coop.project', 'Проекты'),
    ('communities', 'coop.community', 'Сообщества'),
    ('resources', 'coop.resource', 'Ресурсы'),
    ('skills', 'coop.skill.offer', 'Навыки'),
    ('vacancies', 'coop.vacancy', 'Вакансии'),
    ('events', 'coop.event', 'События'),
    ('programs', 'coop.program', 'Программы'),
    ('warehouse', 'coop.warehouse.offer', 'Склады'),
    ('intangibles', 'coop.intangible', 'НМА'),
    ('cfa', 'coop.cfa.issue', 'ЦФА'),
    ('barter', 'coop.barter.offer', 'Бартер'),
]

# Подпись под названием — первое непустое из этих полей.
SUBTITLE_FIELDS = ('coop_specialization_id', 'city', 'category_id')


def _plain(html, limit=220):
    text = re.sub(r'<[^>]+>', ' ', str(html or ''))
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + '…'


class CoopFavorite(models.Model):
    _inherit = 'coop.favorite'

    # ── Карточки ────────────────────────────────────────────────────

    @api.model
    def _coop_card(self, record):
        fields_ = record._fields
        subtitle = ''
        for name in SUBTITLE_FIELDS:
            if name in fields_ and record[name]:
                value = record[name]
                subtitle = value.display_name if hasattr(value, 'display_name') and not isinstance(value, str) else value
                break
        image = False
        if record._name == 'res.partner':
            image = '/web/image/res.partner/%s/avatar_256' % record.id
        elif 'image_512' in fields_ and record.image_512:
            image = '/web/image/%s/%s/image_512' % (record._name, record.id)
        return {
            'model': record._name,
            'id': record.id,
            'name': record.display_name,
            'subtitle': subtitle or '',
            'image': image,
        }

    @api.model
    def _coop_posts(self):
        me = self.env.user.partner_id
        posts = self.env['mail.message'].search([
            ('starred_partner_ids', 'in', me.ids),
            ('model', 'in', WALL_MODELS),
            ('message_type', '=', 'comment'),
        ], order='date desc, id desc', limit=200)
        result = []
        for post in posts.sudo():
            image = post.attachment_ids.filtered(
                lambda a: (a.mimetype or '').startswith('image/'))[:1]
            page = self.env[post.model].sudo().browse(post.res_id).exists()
            result.append({
                'id': post.id,
                'author_id': post.author_id.id,
                'author_name': post.author_id.name or '',
                'page_model': post.model,
                'page_id': post.res_id,
                'page_name': page.display_name if page else '',
                'date': fields.Datetime.to_string(post.date),
                'text': _plain(post.body) or ('Репост' if 'coop_repost_of_id' in post._fields and post.coop_repost_of_id else ''),
                'image': '/web/image/%s/400x300' % image.id if image else False,
                'files': len(post.attachment_ids) - len(image),
            })
        return result

    # ── Для браузера ────────────────────────────────────────────────

    @api.model
    def coop_page(self):
        """Вкладки страницы «Избранное» с карточками."""
        me = self.env.user.partner_id
        marks = self.sudo().search([('partner_id', '=', me.id)])
        by_model = {}
        for mark in marks:
            by_model.setdefault(mark.res_model, []).append(mark.res_id)

        tabs = [{'key': 'posts', 'label': 'Записи', 'items': self._coop_posts()}]
        seen = set()
        for key, model, label in KINDS:
            if model not in self.env or model not in by_model:
                continue
            seen.add(model)
            records = self.env[model].browse(by_model[model]).exists()._filtered_access('read')
            if model == 'res.partner':
                records = records.filtered(lambda r: bool(r.is_company) == (key == 'orgs'))
            items = [self._coop_card(r) for r in records]
            if items:
                tabs.append({'key': key, 'label': label, 'items': items})
        for model, ids in by_model.items():
            if model in seen or model not in self.env:
                continue
            records = self.env[model].browse(ids).exists()._filtered_access('read')
            items = [self._coop_card(r) for r in records]
            if items:
                label = self.env['ir.model']._get(model).name or model
                tabs.append({'key': model, 'label': label, 'items': items})
        return tabs

    @api.model
    def coop_open(self, res_model, res_id):
        """Открыть отмеченное — страницей платформы, если она есть."""
        record = self.env[res_model].browse(int(res_id)).exists()
        if not record:
            return False
        if hasattr(record, 'action_coop_open_page'):
            return record.action_coop_open_page()
        return {
            'type': 'ir.actions.act_window',
            'res_model': res_model,
            'res_id': record.id,
            'views': [[False, 'form']],
        }

    @api.model
    def coop_unstar(self, message_id):
        """Убрать запись стены из избранного (звёздочку движка)."""
        message = self.env['mail.message'].browse(int(message_id)).exists()
        if message and self.env.user.partner_id in message.sudo().starred_partner_ids:
            message.toggle_message_starred()
        return True

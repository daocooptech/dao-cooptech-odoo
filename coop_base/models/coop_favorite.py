# -*- coding: utf-8 -*-
"""Избранное — одно хранилище на все каталоги.

В макете сердечко стоит на каждой карточке во всех каталогах, а рядом с
вкладками раздела — «Избранное» со счётчиком. Владелец 15 сентября 2026:
«добавь сердечки на каждую карточку — это будет добавить в избранное, ты
как то делал такое и мне понравилось».

Одна модель на все разделы, а не поле в каждом каталоге. Разделов
полтора десятка, и отметка «нравится» у них у всех одна и та же: кто,
что, когда. Держать её пятнадцатью полями значило бы пятнадцать раз
писать одно и то же и пятнадцать раз чинить.

Ссылка парой «модель и номер», а не связью: связь пришлось бы заводить
на каждую модель отдельно, и мы вернулись бы к тому же.
"""

from odoo import api, fields, models


class CoopFavorite(models.Model):
    _name = 'coop.favorite'
    _description = 'Избранное'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner', string='Чьё', required=True, index=True,
        ondelete='cascade',
        default=lambda self: self.env.user.partner_id)
    res_model = fields.Char(string='Модель', required=True, index=True)
    res_id = fields.Integer(string='Номер записи', required=True, index=True)

    _sql_constraints = [
        # Второй раз отметить то же самое нельзя: сердечко — не счётчик.
        ('coop_favorite_uniq',
         'unique(partner_id, res_model, res_id)',
         'Эта запись уже в избранном.'),
    ]

    @api.model
    def coop_toggle(self, res_model, res_id):
        """Поставить сердечко или снять. Возвращает, стоит ли оно теперь.

        Через `sudo` намеренно: своё избранное человек ведёт сам, а прав
        писать в модель у рядового участника нет — иначе он мог бы
        завести отметку от чужого имени. Партнёр берётся из учётной
        записи, а не из вызова.
        """
        my_item = self.env.user.partner_id
        was_found = self.sudo().search([
            ('partner_id', '=', my_item.id),
            ('res_model', '=', res_model),
            ('res_id', '=', int(res_id)),
        ], limit=1)
        if was_found:
            was_found.unlink()
            return False
        self.sudo().create({
            'partner_id': my_item.id,
            'res_model': res_model,
            'res_id': int(res_id),
        })
        return True

    @api.model
    def coop_ids_for(self, res_model):
        """Номера записей этого каталога, отмеченных мной.

        Одним запросом на весь экран: иначе канбан из сотни карточек
        спрашивает сервер сто раз.
        """
        records = self.sudo().search([
            ('partner_id', '=', self.env.user.partner_id.id),
            ('res_model', '=', res_model),
        ])
        return records.mapped('res_id')

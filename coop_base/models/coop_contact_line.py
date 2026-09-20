# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopContactLine(models.Model):
    """Свободная строка контактов: человек сам называет способ связи.

    До 20 сентября 2026 в карточке лежал перечень: Skype, мессенджеры,
    социальные сети, приложения. Перечень устаревает быстрее платформы —
    каждый новый способ связи требовал бы своего поля, миграции и места
    в трёх представлениях. Владелец (решение 332) выбрал обратное: одна
    пара «название — значение», сколько нужно строк.

    Строка принадлежит своему хозяину и правится только им: право на
    карточку и право на её строки — одно и то же право.
    """

    _name = 'coop.contact.line'
    _description = 'Строка контактов'
    _order = 'sequence, id'

    partner_id = fields.Many2one(
        'res.partner', 'Владелец', required=True, ondelete='cascade',
        index=True)
    sequence = fields.Integer('Порядок', default=10)
    name = fields.Char('Название', required=True,
                       help='Как называется способ связи: Telegram, GitHub.')
    value = fields.Char('Значение', required=True,
                        help='Адрес, имя в сервисе или ссылка.')

    @api.depends('name', 'value')
    def _compute_display_name(self):
        for line in self:
            line.display_name = '%s: %s' % (line.name or '', line.value or '')

# -*- coding: utf-8 -*-
"""Курс eLearning в каталоге платформы (решение 411).

Штатная модель курса остаётся как есть; здесь — тема и уровень, по
которым раскладываются полки каталога (группировать по многим меткам
курса каталог не умеет: курс оказался бы на нескольких полках сразу), и
подписи для плитки.
"""
from odoo import api, fields, models

TOPICS = [
    ('coop', 'Кооперация и право'),
    ('accounting', 'Учёт и налоги'),
    ('digital', 'Цифровая экономика'),
    ('crafts', 'Ремёсла и производство'),
    ('agro', 'Сельское хозяйство'),
    ('it', 'IT и разработка'),
    ('design', 'Дизайн и медиа'),
    ('management', 'Управление и проекты'),
    ('safety', 'Здоровье и безопасность'),
    ('language', 'Языки и общение'),
    ('ecology', 'Экология'),
]

LEVELS = [
    ('basic', 'Начальный'),
    ('middle', 'Средний'),
    ('advanced', 'Продвинутый'),
]


def _plural(n, one, few, many):
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


class SlideChannel(models.Model):
    _inherit = 'slide.channel'

    coop_topic = fields.Selection(TOPICS, string='Тема', index=True)
    coop_level = fields.Selection(LEVELS, string='Уровень', default='basic')
    coop_author_id = fields.Many2one(related='user_id.partner_id', string='Автор')
    coop_lessons_label = fields.Char(compute='_compute_coop_labels')
    coop_members_label = fields.Char(compute='_compute_coop_labels')
    coop_progress_label = fields.Char(compute='_compute_coop_progress')

    @api.depends('total_slides', 'total_time', 'members_count')
    def _compute_coop_labels(self):
        for channel in self:
            lessons = channel.total_slides or 0
            hours = channel.total_time or 0
            if hours >= 1:
                duration = '%s ч' % ('%g' % round(hours, 1)).replace('.', ',')
            else:
                duration = '%s мин' % int(round(hours * 60))
            channel.coop_lessons_label = '%s %s · %s' % (
                lessons, _plural(lessons, 'урок', 'урока', 'уроков'), duration) if lessons else ''
            members = channel.members_count or 0
            channel.coop_members_label = '%s %s' % (
                members, _plural(members, 'ученик', 'ученика', 'учеников')) if members else 'Пока без учеников'

    def _compute_coop_progress(self):
        for channel in self:
            if channel.is_member:
                done = channel.completion or 0
                channel.coop_progress_label = 'Пройден' if done >= 100 else 'Пройдено %s%%' % done
            else:
                channel.coop_progress_label = ''

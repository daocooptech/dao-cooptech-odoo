# -*- coding: utf-8 -*-
from odoo import models


class SlideChannel(models.Model):
    """Панель фильтров каталога курсов.

    Панели не было (задача 422). Макет `ext-education.html` — заглушка без
    каталога, поэтому набор взят из того, чем курс отличается от курса:
    тема, уровень, автор, длительность и «мои курсы». Формат (курс или
    документация) и порядок записи не взяты: у всех курсов каталога они
    одинаковые — выбор из одного значения ничего не отбирает.
    """
    _inherit = 'slide.channel'

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
            # Условия панели, кроме условий на само поле: иначе выбор
            # одного значения обнулил бы счётчики у остальных.
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        # Без sudo: считать ровно то, что человеку покажет каталог.
        def counts(field, dom):
            return dict(self._read_group(dom, [field], ['__count']))

        topic_counts = counts('coop_topic', without('coop_topic'))
        level_counts = counts('coop_level', without('coop_level'))
        authors = sorted({u.name for u in counts('user_id', base) if u})
        # Состав курса (`channel_partner_ids`) закрыт правами для
        # участника — свои записи выбираем отдельно, только свои.
        rows = self.env['slide.channel.partner'].sudo().search([
            ('partner_id', '=', self.env.user.partner_id.id),
            ('member_status', '!=', 'invited')])
        mine = rows.channel_id.ids
        done = rows.filtered(
            lambda r: r.member_status == 'completed').channel_id.ids
        return [
            {'code': 'topic', 'label': 'Тема',
             'widget': 'select', 'field': 'coop_topic', 'operator': '=',
             'placeholder': 'Любая', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': topic_counts.get(code, 0)}
                         for code, label in self._fields['coop_topic'].selection
                         if topic_counts.get(code)]},
            {'code': 'level', 'label': 'Уровень',
             'hint': 'Начальный — без подготовки. Продвинутый — для тех, '
                     'кто уже работает в этой области.',
             'widget': 'select', 'field': 'coop_level', 'operator': '=',
             'placeholder': 'Любой', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': level_counts.get(code, 0)}
                         for code, label in self._fields['coop_level'].selection]},
            {'code': 'author', 'label': 'Автор',
             'widget': 'text', 'field': 'user_id.name', 'operator': 'ilike',
             'placeholder': 'Начните вводить имя',
             'options': [{'value': a, 'label': a} for a in authors]},
            {'code': 'duration', 'label': 'Длительность, ч',
             'hint': 'Сумма времени всех уроков. Пустое поле — без '
                     'ограничения.',
             'widget': 'range', 'field': 'total_time'},
            # Приглашение без записи участием не считается.
            {'code': 'mine', 'label': 'Участие', 'widget': 'quick',
             'options': [{'value': 'mine', 'label': 'Только мои курсы',
                          'domain': [('id', 'in', mine)]},
                         {'value': 'done', 'label': 'Пройденные мной',
                          'domain': [('id', 'in', done)]}]},
        ]

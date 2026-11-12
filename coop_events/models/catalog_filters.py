# -*- coding: utf-8 -*-
from odoo import models


class CoopEvent(models.Model):
    """Панель фильтров каталога событий (задача 422).

    Набор — чем событие отличается от события: вид, формат, состояние
    записи, город, даты, свободные места и «куда я записан».
    """
    _inherit = 'coop.event'

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

        def select(code, label, field, placeholder, hint=None):
            got = counts(field, without(field))
            block = {'code': code, 'label': label, 'widget': 'select',
                     'field': field, 'operator': '=',
                     'placeholder': placeholder, 'counted': True,
                     'options': [{'value': v, 'label': t, 'count': got.get(v, 0)}
                                 for v, t in self._fields[field].selection
                                 if got.get(v)]}
            if hint:
                block['hint'] = hint
            return block

        cities = sorted(c for c in counts('city', base) if c)
        return [
            select('category', 'Вид события', 'category', 'Любой'),
            select('format', 'Формат', 'format', 'Любой',
                   'Смешанный — можно прийти или подключиться.'),
            select('state', 'Состояние', 'state', 'Любое',
                   'Идёт запись — места ещё можно занять.'),
            {'code': 'city', 'label': 'Город',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            {'code': 'date', 'label': 'Даты',
             'hint': 'Когда событие начинается.',
             'widget': 'daterange', 'field': 'date_start', 'datetime': True},
            {'code': 'quick', 'label': 'Быстрый отбор', 'widget': 'quick',
             'options': [
                 {'value': 'upcoming', 'label': 'Ещё не прошли',
                  'domain': [('is_past', '=', False),
                             ('state', '!=', 'cancelled')]},
                 {'value': 'seats', 'label': 'Есть свободные места',
                  'domain': [('state', '=', 'open'),
                             '|', ('capacity', '=', 0),
                             ('seats_left', '>', 0)]},
                 {'value': 'signed', 'label': 'Куда я записан',
                  'domain': [('am_i_signed', '=', True)]},
             ]},
        ]

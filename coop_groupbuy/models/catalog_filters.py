# -*- coding: utf-8 -*-
from odoo import models


class CoopGroupbuy(models.Model):
    """Панель фильтров каталога совместных закупок (задача 422).

    Набор — раздел, состояние, город, цена сейчас, набрано и стоп-дата;
    быстрый отбор — «можно вступить» и «где я участвую».
    """
    _inherit = 'coop.groupbuy'

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
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
            select('category', 'Раздел', 'category', 'Любой'),
            select('state', 'Состояние', 'state', 'Любое',
                   'Идёт сбор — заказ ещё можно добавить.'),
            {'code': 'city', 'label': 'Город',
             'hint': 'Где пункт выдачи.',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            {'code': 'price', 'label': 'Цена сейчас, ₽',
             'hint': 'Цена за единицу при набранном объёме, со сбором '
                     'организатора. Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'current_price'},
            {'code': 'progress', 'label': 'Набрано, %',
             'hint': 'Доля от минимального объёма, при котором поставщик '
                     'везёт.',
             'widget': 'range', 'field': 'progress'},
            {'code': 'stop', 'label': 'Сбор до',
             'hint': 'Когда закрывается приём заказов.',
             'widget': 'daterange', 'field': 'stop_date'},
            {'code': 'quick', 'label': 'Быстрый отбор', 'widget': 'quick',
             'options': [
                 {'value': 'open', 'label': 'Можно вступить',
                  'domain': [('state', '=', 'collecting')]},
                 {'value': 'mine', 'label': 'Где я участвую',
                  'domain': [('is_participant', '=', True)]},
             ]},
        ]

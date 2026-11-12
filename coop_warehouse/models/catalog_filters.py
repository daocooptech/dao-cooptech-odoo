# -*- coding: utf-8 -*-
from odoo import models


class CoopWarehouseOffer(models.Model):
    """Панель фильтров биржи складских мощностей (задача 422).

    Набор — сторона, вид хранения, город, объём, единица, цена, сроки,
    состояние; быстрый отбор — «мои объявления».
    """
    _inherit = 'coop.warehouse.offer'

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
            select('side', 'Сторона', 'side', 'Любая'),
            select('storage', 'Вид хранения', 'storage_kind', 'Любой'),
            {'code': 'city', 'label': 'Город',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            select('unit', 'Единица объёма', 'capacity_unit', 'Любая',
                   'Объём ниже сравнивается в выбранной единице.'),
            {'code': 'volume', 'label': 'Объём',
             'widget': 'range', 'field': 'volume'},
            {'code': 'price', 'label': 'Цена, ₽',
             'hint': 'Самое дешёвое из денежных условий объявления.',
             'widget': 'range', 'field': 'main_price'},
            {'code': 'from', 'label': 'Срок с',
             'widget': 'daterange', 'field': 'date_from'},
            select('state', 'Состояние', 'state', 'Любое'),
            {'code': 'quick', 'label': 'Быстрый отбор', 'widget': 'quick',
             'options': [
                 {'value': 'mine', 'label': 'Мои объявления',
                  'domain': [('is_mine', '=', True)]},
             ]},
        ]

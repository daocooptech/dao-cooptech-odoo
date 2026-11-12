# -*- coding: utf-8 -*-
from odoo import models


class CoopProgram(models.Model):
    """Панель фильтров каталога целевых программ (задача 422).

    Набор — отрасль, состояние, город, фонд, срок; быстрый отбор —
    «идёт набор» и «где я участвую».
    """
    _inherit = 'coop.program'

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
            select('industry', 'Отрасль', 'industry', 'Любая'),
            select('state', 'Состояние', 'state', 'Любое',
                   'Набор участников — вступить можно сейчас.'),
            {'code': 'city', 'label': 'Город',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            {'code': 'fund', 'label': 'Фонд программы, ₽',
             'hint': 'Сколько собрано на общие закупки и работы. Пустое '
                     'поле — без ограничения.',
             'widget': 'range', 'field': 'fund_amount'},
            {'code': 'duration', 'label': 'Срок, месяцев',
             'widget': 'range', 'field': 'duration_months'},
            {'code': 'quick', 'label': 'Быстрый отбор', 'widget': 'quick',
             'options': [
                 {'value': 'collecting', 'label': 'Идёт набор участников',
                  'domain': [('state', '=', 'collecting')]},
                 {'value': 'mine', 'label': 'Где я участвую',
                  'domain': [('is_participant', '=', True)]},
             ]},
        ]

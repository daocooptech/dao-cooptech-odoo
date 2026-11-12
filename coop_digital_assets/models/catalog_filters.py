# -*- coding: utf-8 -*-
from odoo import models


class CoopCfaIssue(models.Model):
    """Панель фильтров каталога ЦФА.

    Панели не было (задача 422). Набор — по макету `cfa-catalog.html`:
    вид прав и состояние выпуска; «Кому доступен» из макета не взят —
    поля о квалификации покупателя у выпуска нет, отбор по нему врал бы.
    Сверх макета — оператор, город эмитента и объём выпуска.
    """
    _inherit = 'coop.cfa.issue'

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        # Без sudo: считать ровно то, что человеку покажет каталог.
        def counts(field, dom):
            return {(value.id if hasattr(value, 'id') else value): count
                    for value, count in self._read_group(dom, [field], ['__count'])}

        kind_counts = counts('rights_kind', without('rights_kind'))
        state_counts = counts('state', without('state'))
        operator_counts = counts('operator_id', without('operator_id'))
        operators = self.env['coop.cfa.operator'].sudo().browse(
            [oid for oid in operator_counts if oid])
        # Город — у эмитента, у выпуска он не хранится: подсказки
        # собираются по эмитентам выпусков раздела.
        cities = sorted({c for c in self.search(base).mapped('city') if c})
        return [
            {'code': 'rights_kind', 'label': 'Вид прав',
             'hint': 'Что удостоверяет выпуск. Перечень закрыт статьёй 1 '
                     'закона 259-ФЗ.',
             'widget': 'select', 'field': 'rights_kind', 'operator': '=',
             'placeholder': 'Любой', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': kind_counts.get(code, 0)}
                         for code, label in self._fields['rights_kind'].selection]},
            {'code': 'state', 'label': 'Состояние выпуска',
             'hint': 'Приобрести можно выпущенное.',
             'widget': 'select', 'field': 'state', 'operator': '=',
             'placeholder': 'Любое', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': state_counts.get(code, 0)}
                         for code, label in self._fields['state'].selection
                         if state_counts.get(code)]},
            {'code': 'operator', 'label': 'Оператор',
             'hint': 'Через кого идёт выпуск: платформа или сторонний '
                     'оператор из реестра Банка России.',
             'widget': 'select', 'field': 'operator_id', 'operator': '=',
             'number': True, 'placeholder': 'Любой', 'counted': True,
             'options': [{'value': o.id, 'label': o.name,
                          'count': operator_counts.get(o.id, 0)}
                         for o in operators.sorted('sequence')]},
            {'code': 'city', 'label': 'Город эмитента',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            {'code': 'amount', 'label': 'Объём выпуска, ₽',
             'hint': 'Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'amount'},
        ]

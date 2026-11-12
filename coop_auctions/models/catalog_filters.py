# -*- coding: utf-8 -*-
from odoo import models


class CoopAuction(models.Model):
    """Панель фильтров каталога аукционов.

    Панели не было: справа стояло «пока отбирают порядком и поиском»
    (задача 422, владелец 12.11.2026: «очень важно, чтобы были сделаны
    качественно все фильтры»). В макете `ext-auctions.html` панели нет —
    набор взят из того, чем торг отличается от торга: вид (на повышение
    или редукцион), состояние, город, текущая цена.
    """
    _inherit = 'coop.auction'

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

        kind_counts = counts('kind', without('kind'))
        state_counts = counts('state', without('state'))
        cities = sorted(c for c in counts('city', base) if c)
        return [
            {'code': 'kind', 'label': 'Вид торга',
             'hint': 'На повышение — продают, побеждает бóльшая ставка. '
                     'Редукцион — ищут исполнителя, побеждает меньшая цена.',
             'widget': 'select', 'field': 'kind', 'operator': '=',
             'placeholder': 'Любой', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': kind_counts.get(code, 0)}
                         for code, label in self._fields['kind'].selection]},
            {'code': 'state', 'label': 'Состояние',
             'hint': 'Идут торги — ставку можно сделать сейчас.',
             'widget': 'select', 'field': 'state', 'operator': '=',
             'placeholder': 'Любое', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': state_counts.get(code, 0)}
                         for code, label in self._fields['state'].selection
                         if state_counts.get(code)]},
            {'code': 'city', 'label': 'Город',
             'hint': 'Где лот: забирать, вывозить или выполнять работу.',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            {'code': 'price', 'label': 'Текущая цена, ₽',
             'hint': 'Последняя ставка, а без ставок — стартовая цена. '
                     'Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'current_price'},
        ]

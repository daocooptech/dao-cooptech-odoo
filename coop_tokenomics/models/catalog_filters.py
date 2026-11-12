# -*- coding: utf-8 -*-
from odoo import models


def _helpers(model, domain):
    base = list(model.env.context.get('coop_base_domain') or [])

    def without(*fields_):
        # Условия панели, кроме условий на само поле: иначе выбор
        # одного значения обнулил бы счётчики у остальных.
        return base + [leaf for leaf in domain or []
                       if not (isinstance(leaf, (list, tuple)) and leaf
                               and leaf[0] in fields_)]

    # Без sudo: считать ровно то, что человеку покажет каталог.
    def counts(field, dom):
        return dict(model._read_group(dom, [field], ['__count']))

    def select(code, label, field, placeholder, hint=None):
        got = counts(field, without(field))
        block = {'code': code, 'label': label, 'widget': 'select',
                 'field': field, 'operator': '=',
                 'placeholder': placeholder, 'counted': True,
                 'options': [{'value': v, 'label': t, 'count': got.get(v, 0)}
                             for v, t in model._fields[field]._description_selection(model.env)
                             if got.get(v)]}
        if hint:
            block['hint'] = hint
        return block

    return base, without, counts, select


class CoopCession(models.Model):
    """Панель фильтров витрины уступок (задача 422).

    Набор — состояние, должник, сумма долга, цена, дисконт, срок
    платежа; быстрый отбор — «можно купить» и «мои уступки».
    """
    _inherit = 'coop.cession'

    def _coop_catalog_filters(self, domain):
        base, without, counts, select = _helpers(self, domain)
        return [
            select('state', 'Состояние', 'state', 'Любое',
                   'Размещено — право требования ещё можно купить.'),
            {'code': 'debtor', 'label': 'Должник',
             'widget': 'text', 'field': 'debtor_id.name', 'operator': 'ilike',
             'placeholder': 'Начните вводить название или имя'},
            {'code': 'amount', 'label': 'Сумма долга, ₽',
             'widget': 'range', 'field': 'amount'},
            {'code': 'price', 'label': 'Цена уступки, ₽',
             'widget': 'range', 'field': 'price'},
            {'code': 'discount', 'label': 'Дисконт, %',
             'hint': 'Насколько цена ниже суммы долга.',
             'widget': 'range', 'field': 'discount_percent'},
            {'code': 'due', 'label': 'Срок платежа',
             'hint': 'Когда должник обязан заплатить.',
             'widget': 'daterange', 'field': 'due_date'},
            {'code': 'quick', 'label': 'Быстрый отбор', 'widget': 'quick',
             'options': [
                 {'value': 'open', 'label': 'Можно купить',
                  'domain': [('state', 'in', ('published', 'negotiating'))]},
                 {'value': 'mine', 'label': 'Мои уступки',
                  'domain': [('is_mine', '=', True)]},
             ]},
        ]


class CoopTokenOrder(models.Model):
    """Панель фильтров биржи токенов (задача 422).

    Набор — раздел ресурса, сторона, вид продажи, состояние, цена за
    единицу, срок поставки. Валюта расчёта не взята: у всех заявок она
    одна — выбор из одного значения ничего не отбирает.
    """
    _inherit = 'coop.token.order'

    def _coop_catalog_filters(self, domain):
        base, without, counts, select = _helpers(self, domain)
        got = counts('resource_category_id', without('resource_category_id'))
        return [
            {'code': 'category', 'label': 'Раздел',
             'hint': 'Какой ресурс обеспечивает токен.',
             'widget': 'select', 'field': 'resource_category_id',
             'operator': '=', 'placeholder': 'Любой', 'counted': True,
             'options': [{'value': c.id, 'label': c.display_name,
                          'count': n}
                         for c, n in sorted(((c, n) for c, n in got.items()
                                             if c),
                                            key=lambda i: i[0].display_name)]},
            select('side', 'Сторона', 'side', 'Любая',
                   'Продажа — токен предлагают. Покупка — ищут.'),
            select('kind', 'Вид продажи', 'kind', 'Любой',
                   'Первичная — от того, кто выпустил токен. '
                   'Перепродажа — от прежнего покупателя.'),
            select('state', 'Состояние', 'state', 'Любое',
                   'В стакане — заявка ждёт встречной.'),
            {'code': 'price', 'label': 'Цена за единицу',
             'widget': 'range', 'field': 'price_per_unit'},
            {'code': 'delivery', 'label': 'Срок поставки',
             'hint': 'Когда ресурс по токену можно получить.',
             'widget': 'daterange', 'field': 'delivery_date'},
        ]

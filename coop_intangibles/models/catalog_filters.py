# -*- coding: utf-8 -*-
from odoo import models


class CoopIntangible(models.Model):
    """Панель фильтров каталога НМА (задача 422).

    Набор — вид актива, состояние права, залог, правообладатель,
    остаточная стоимость, срок охраны; быстрый отбор — «можно взять
    лицензию» и «мои активы».
    """
    _inherit = 'coop.intangible'

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
                                 for v, t in self._fields[field]._description_selection(self.env)
                                 if got.get(v)]}
            if hint:
                block['hint'] = hint
            return block

        return [
            select('kind', 'Вид актива', 'kind', 'Любой'),
            select('state', 'Состояние права', 'state', 'Любое'),
            select('pledge', 'Залог', 'pledge_state', 'Любой',
                   'Обеспечением актив становится только после '
                   'регистрации залога там, где велит закон.'),
            {'code': 'owner', 'label': 'Правообладатель',
             'widget': 'text', 'field': 'owner_id.name', 'operator': 'ilike',
             'placeholder': 'Начните вводить название или имя'},
            {'code': 'value', 'label': 'Остаточная стоимость, ₽',
             'hint': 'Первоначальная стоимость минус накопленная '
                     'амортизация. Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'residual_value'},
            {'code': 'protection', 'label': 'Охрана до',
             'hint': 'Когда истекает срок правовой охраны.',
             'widget': 'daterange', 'field': 'protection_until'},
            {'code': 'quick', 'label': 'Быстрый отбор', 'widget': 'quick',
             'options': [
                 {'value': 'license', 'label': 'С действующими лицензиями',
                  'domain': [('license_ids', 'any',
                              [('state', '=', 'active')])]},
                 {'value': 'mine', 'label': 'Мои активы',
                  'domain': [('is_mine', '=', True)]},
             ]},
        ]


class CoopIntangibleLicense(models.Model):
    """Панель фильтров каталога лицензий (задача 422).

    Набор — вид актива, состояние лицензии, исключительность,
    территория, цена, роялти, срок; быстрый отбор — «мои лицензии»
    (выданные мне или моими организациями и выданные мной).
    """
    _inherit = 'coop.intangible.license'

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        def counts(field, dom):
            return dict(self._read_group(dom, [field], ['__count']))

        def select(code, label, field, placeholder):
            got = counts(field, without(field))
            return {'code': code, 'label': label, 'widget': 'select',
                    'field': field, 'operator': '=',
                    'placeholder': placeholder, 'counted': True,
                    'options': [{'value': v, 'label': t, 'count': got.get(v, 0)}
                                for v, t in self._fields[field]._description_selection(self.env)
                                if got.get(v)]}

        territories = sorted(t for t in counts('territory', base) if t)
        mine = self.env['coop.intangible']._my_partners().ids
        return [
            select('kind', 'Вид актива', 'kind', 'Любой'),
            select('state', 'Состояние', 'state', 'Любое'),
            {'code': 'territory', 'label': 'Территория',
             'widget': 'text', 'field': 'territory', 'operator': 'ilike',
             'placeholder': 'Начните вводить',
             'options': [{'value': t, 'label': t} for t in territories]},
            {'code': 'price', 'label': 'Цена, ₽',
             'hint': 'Паушальный платёж. Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'price'},
            {'code': 'royalty', 'label': 'Роялти, %',
             'widget': 'range', 'field': 'royalty_percent'},
            {'code': 'ends', 'label': 'Действует до',
             'widget': 'daterange', 'field': 'ends_on'},
            {'code': 'quick', 'label': 'Быстрый отбор', 'widget': 'quick',
             'options': [
                 {'value': 'active', 'label': 'Только действующие',
                  'domain': [('state', '=', 'active')]},
                 # Исключительная — кроме лицензиата, никто, включая
                 # правообладателя, на этой территории не использует.
                 {'value': 'exclusive', 'label': 'Только исключительные',
                  'domain': [('is_exclusive', '=', True)]},
                 # Лицензию видят только её стороны (rule_intangible_license_side),
                 # так что «мои» — это весь список: отбор «Мои лицензии»
                 # показывал 74 из 74 (задача 432). Полезно другое — с какой
                 # стороны договора участник.
                 {'value': 'granted', 'label': 'Выданные мной',
                  'domain': [('licensor_id', 'in', mine)]},
                 {'value': 'received', 'label': 'Полученные мной',
                  'domain': [('licensee_id', 'in', mine)]},
             ]},
        ]

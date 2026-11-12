# -*- coding: utf-8 -*-
from odoo import models


class CoopCommunity(models.Model):
    """Панель фильтров каталога сообществ.

    Панели не было (задача 422). Набор — по макету `communities.html`:
    тип сообщества, город, «только те, где я состою»; сверх макета —
    порог входа (открытое, по заявке, закрытое): без него не понять,
    куда можно вступить сразу.
    """
    _inherit = 'coop.community'

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        # Без sudo: считать ровно то, что человеку покажет каталог.
        def counts(field, dom):
            return dict(self._read_group(dom, [field], ['__count']))

        kind_counts = counts('kind', without('kind'))
        access_counts = counts('access', without('access'))
        cities = sorted(c for c in counts('city', base) if c)
        partner = self.env.user.partner_id
        return [
            {'code': 'kind', 'label': 'Тип сообщества',
             'hint': 'По какому признаку объединены участники.',
             'widget': 'select', 'field': 'kind', 'operator': '=',
             'placeholder': 'Любой', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': kind_counts.get(code, 0)}
                         for code, label in self._fields['kind'].selection]},
            {'code': 'city', 'label': 'Город',
             'hint': '«Удалённо» — сообщества без привязки к городу.',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            {'code': 'access', 'label': 'Кто может вступить',
             'hint': 'Открытое — вступают сами. По заявке — решает '
                     'модератор. Закрытое — состав и обсуждение видят '
                     'только участники.',
             'widget': 'select', 'field': 'access', 'operator': '=',
             'placeholder': 'Любое', 'counted': True,
             'options': [{'value': code, 'label': label,
                          'count': access_counts.get(code, 0)}
                         for code, label in self._fields['access'].selection]},
            # Участие — строка состава с этим человеком в состоянии
            # «участник»: одной строкой, иначе «состою» и «вышел» из
            # разных строк сложились бы в ложное «да».
            {'code': 'joined', 'label': 'Участие', 'widget': 'quick',
             'options': [{'value': 'joined',
                          'label': 'Только те, где я состою',
                          'domain': [('member_ids', 'any', [
                              ('partner_id', '=', partner.id),
                              ('state', '=', 'active')])]}]},
        ]

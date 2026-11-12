# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopDeal(models.Model):
    """Панель фильтров каталога сделок.

    Панели не было (задача 422). Набор — по макету `deals.html`:
    состояние, что передаётся, способ, итог для доверия, контрагент
    (человек или организация), город и даты (в макете — год; диапазон
    дат отбирает и год, и любой его кусок).
    """
    _inherit = 'coop.deal'

    coop_counterparty_kind = fields.Selection([
        ('person', 'Человек'),
        ('company', 'Организация'),
    ], string='Контрагент', compute='_compute_coop_counterparty_kind',
        search='_search_coop_counterparty_kind',
        help='Кто вторая сторона сделки глазами смотрящего.')

    @api.depends_context('uid')
    @api.depends('party_a_id', 'party_b_id')
    def _compute_coop_counterparty_kind(self):
        for deal in self:
            other = deal._other_partner()
            deal.coop_counterparty_kind = (
                other and ('company' if other.is_company else 'person'))

    def _search_coop_counterparty_kind(self, operator, value):
        # Вторая сторона — та, что не я. В чужой сделке (её видит,
        # например, правление) «моей» стороны нет, и контрагентом
        # считается любая из двух.
        if operator == 'in':
            values = set(value)
        elif operator == '=':
            values = {value}
        else:
            return NotImplemented
        if values >= {'person', 'company'}:
            return [('id', '!=', False)]
        if not values & {'person', 'company'}:
            return [('id', '=', False)]
        company = 'company' in values
        mine = self.env.user.coop_actor_partner_ids.ids
        return ['|', '|',
                '&', ('party_a_id', 'in', mine),
                ('party_b_id.is_company', '=', company),
                '&', ('party_b_id', 'in', mine),
                ('party_a_id.is_company', '=', company),
                '&', '&', ('party_a_id', 'not in', mine),
                ('party_b_id', 'not in', mine),
                '|', ('party_a_id.is_company', '=', company),
                ('party_b_id.is_company', '=', company)]

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        # Без sudo: считать ровно то, что человеку покажет каталог.
        def counts(field, dom):
            return dict(self._read_group(dom, [field], ['__count']))

        def select(code, label, field, hint, placeholder, only_present=False):
            found = counts(field, without(field))
            return {'code': code, 'label': label, 'hint': hint,
                    'widget': 'select', 'field': field, 'operator': '=',
                    'placeholder': placeholder, 'counted': True,
                    'options': [{'value': key, 'label': text,
                                 'count': found.get(key, 0)}
                                for key, text in self._fields[field].selection
                                if found.get(key) or not only_present]}

        party_base = without('coop_counterparty_kind')
        cities = sorted(c for c in counts('city', base) if c)
        return [
            select('state', 'Состояние', 'state',
                   'Завершённые уже оценены обеими сторонами и попали в '
                   'расчёт доверия; остальные — нет.', 'Любое', True),
            select('subject', 'Что передаётся', 'subject',
                   'Предмет сделки: вещь или материал, услуга, работа по '
                   'вакансии, вклад в проект или взаимный кредит.', 'Любое'),
            select('way', 'Способ', 'way',
                   'Те же способы получения, что в каталоге ресурсов.',
                   'Любой', True),
            select('outcome', 'Итог для доверия', 'outcome',
                   'Как сделка учтена в уровне доверия сторон.', 'Любой', True),
            {'code': 'counterparty', 'label': 'Контрагент',
             'hint': 'Кто вторая сторона: человек или организация.',
             'widget': 'select', 'field': 'coop_counterparty_kind',
             'operator': '=', 'placeholder': 'Любой', 'counted': True,
             'options': [{'value': key, 'label': text,
                          'count': self.search_count(party_base + [
                              ('coop_counterparty_kind', '=', key)])}
                         for key, text in
                         self._fields['coop_counterparty_kind'].selection]},
            {'code': 'city', 'label': 'Город',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город',
             'options': [{'value': c, 'label': c} for c in cities]},
            {'code': 'date', 'label': 'Дата сделки',
             'hint': 'Заключённая — по дню заключения, обращение и '
                     'переговоры — по дню появления. Пустое поле — без '
                     'ограничения.',
             'widget': 'daterange', 'field': 'funnel_date'},
        ]

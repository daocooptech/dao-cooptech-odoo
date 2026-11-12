# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields, models


class CoopProject(models.Model):
    """Панель фильтров каталога проектов.

    Её не было ни в одной линии: справа стояло «В этом разделе пока
    отбирают порядком и поиском по названию» (владелец 12.11.2026:
    «куда-то опять исчезли фильтры из каталога проектов»; «очень важно,
    чтобы были сделаны качественно все фильтры»). Набор — по макету
    `projects.html`: город, тема с разделом, готовность, экономическая
    модель; сверх макета — состояние сбора и «срок на исходе», которые
    были в штатном поиске, но до панели не доходили.
    """
    _inherit = 'coop.project'

    _COOP_READINESS_STEPS = (90, 75, 50)

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
            # Условия панели, кроме условий на само поле: иначе выбор одной
            # темы обнулил бы счётчики у остальных.
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        def chosen(field):
            return next((leaf[2] for leaf in domain or []
                         if isinstance(leaf, (list, tuple)) and len(leaf) == 3
                         and leaf[0] == field), None)

        # Без sudo: считать ровно то, что человеку покажет каталог.
        def counts(field, dom):
            return {(value.id if hasattr(value, 'id') else value): count
                    for value, count in self._read_group(dom, [field], ['__count'])}

        cities = sorted(c for c in counts('city', base) if c)
        blocks = [{
            'code': 'city', 'label': 'Город',
            'hint': 'Показать проекты только из выбранного города.',
            'widget': 'text', 'field': 'city', 'operator': 'ilike',
            'placeholder': 'Начните вводить город',
            'options': [{'value': c, 'label': c} for c in cities],
        }]

        Category = self.env['coop.project.category'].sudo()
        category_counts = counts('category_id',
                                 without('category_id', 'subcategory_id'))
        blocks.append({
            'code': 'category', 'label': 'Тема',
            'hint': 'О чём проект: экология, технологии, образование и другие.',
            'widget': 'select', 'field': 'category_id', 'operator': '=',
            'number': True, 'placeholder': 'Любая', 'counted': True,
            'reload': True,
            'options': [{'value': c.id, 'label': c.name,
                         'count': category_counts.get(c.id, 0)}
                        for c in Category.search([('parent_id', '=', False)],
                                                 order='name')
                        if category_counts.get(c.id)],
        })
        category = chosen('category_id')
        if category:
            sub_counts = counts('subcategory_id', without('subcategory_id'))
            subs = Category.search([('parent_id', '=', int(category))], order='name')
            options = [{'value': s.id, 'label': s.name,
                        'count': sub_counts.get(s.id, 0)}
                       for s in subs if sub_counts.get(s.id)]
            if options:
                blocks.append({
                    'code': 'subcategory', 'label': 'Раздел',
                    'widget': 'select', 'field': 'subcategory_id',
                    'operator': '=', 'number': True, 'placeholder': 'Любой',
                    'counted': True, 'options': options,
                })

        kind_counts = counts('kind', without('kind'))
        blocks.append({
            'code': 'kind', 'label': 'Экономическая модель',
            'hint': 'Кто и как получает отдачу от участия: пай с правом '
                    'голоса, доля, безвозвратный вклад или токены управления.',
            'widget': 'select', 'field': 'kind', 'operator': '=',
            'placeholder': 'Любая', 'counted': True,
            'options': [{'value': code, 'label': label,
                         'count': kind_counts.get(code, 0)}
                        for code, label in self._fields['kind'].selection],
        })

        state_counts = counts('state', without('state'))
        blocks.append({
            'code': 'state', 'label': 'Состояние',
            'hint': 'Сбор — проект ищет людей, ресурсы и деньги. Запущен — '
                    'собранного хватило, идут работы.',
            'widget': 'select', 'field': 'state', 'operator': '=',
            'placeholder': 'Любое', 'counted': True,
            'options': [{'value': code, 'label': label,
                         'count': state_counts.get(code, 0)}
                        for code, label in self._fields['state'].selection
                        if state_counts.get(code)],
        })

        readiness_base = without('readiness')
        blocks.append({
            'code': 'readiness', 'label': 'Готовность',
            'hint': 'Собрано против нужного — сумма принятых вкладов к оценке '
                    'всех потребностей проекта.',
            'widget': 'select', 'field': 'readiness', 'operator': '>=',
            'number': True, 'placeholder': 'Любая', 'counted': True,
            'options': [{'value': step, 'label': f'От {step}%',
                         'count': self.search_count(
                             readiness_base + [('readiness', '>=', step)])}
                        for step in self._COOP_READINESS_STEPS],
        })

        # По дате, а не по «осталось дней»: то поле не хранится, и домен с
        # ним Odoo отвергает (так же сделан фильтр в штатном поиске).
        soon = fields.Date.to_string(
            fields.Date.context_today(self) + timedelta(days=7))
        blocks.append({
            'code': 'deadline', 'label': 'Срок', 'widget': 'quick',
            'options': [{'value': 'soon', 'label': 'Сбор кончается за неделю',
                         'domain': [('state', '=', 'gathering'),
                                    ('date_deadline', '<=', soon)]}],
        })
        return blocks

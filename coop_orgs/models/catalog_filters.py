# -*- coding: utf-8 -*-
from odoo import models


class ResPartner(models.Model):
    """Панель фильтров каталога организаций.

    Люди и организации — одна модель, и панель людей (`coop_people`)
    отвечает только своему каталогу. У организаций панели не было вовсе:
    справа стояло «В этом разделе пока отбирают порядком и поиском по
    названию» (владелец 27.09.2026: «куда делись фильтры организаций?
    почини»). Набор — по макету `organizations.html`: отрасль с
    подкатегорией, тип (группа форм) с уточнением формы, город, уровень
    доверия; плюс вид кооператива (решение 425).
    """
    _inherit = 'res.partner'

    _COOP_ORG_TRUST_STEPS = (90, 75, 50)

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])
        leaves = [tuple(leaf) for leaf in base
                  if isinstance(leaf, (list, tuple)) and len(leaf) == 3]
        if ('is_company', '=', True) not in leaves:
            parent = getattr(super(), '_coop_catalog_filters', None)
            return parent(domain) if parent else []

        def without(*fields_):
            # Условия панели, кроме условий на само поле: иначе выбор одной
            # отрасли обнулил бы счётчики у остальных.
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

        def chosen(field):
            return next((leaf[2] for leaf in domain or []
                         if isinstance(leaf, (list, tuple)) and len(leaf) == 3
                         and leaf[0] == field), None)

        # Без sudo: считать ровно то, что человеку покажет каталог.
        orgs = self

        def counts(field, dom):
            return {(value.id if hasattr(value, 'id') else value): count
                    for value, count in orgs._read_group(dom, [field], ['__count'])}

        Okved = self.env['coop.okved'].sudo()
        section_counts = counts('coop_okved_section_id',
                                without('coop_okved_section_id', 'coop_okved_id'))
        sections = Okved.search([('parent_id', '=', False)], order='code')
        blocks = [{
            'code': 'section', 'label': 'Отрасль',
            'hint': 'Раздел ОКВЭД — чем организация занимается.',
            'widget': 'select', 'field': 'coop_okved_section_id',
            'operator': '=', 'placeholder': 'Любая', 'counted': True,
            'reload': True,
            'options': [{'value': s.id, 'label': s.display_name,
                         'count': section_counts.get(s.id, 0)}
                        for s in sections if section_counts.get(s.id)],
        }]
        section = chosen('coop_okved_section_id')
        if section:
            okved_counts = counts('coop_okved_id', without('coop_okved_id'))
            classes = Okved.search([('parent_id', '=', int(section))], order='code')
            blocks.append({
                'code': 'okved', 'label': 'Подкатегория',
                'widget': 'select', 'field': 'coop_okved_id',
                'operator': '=', 'placeholder': 'Любая', 'counted': True,
                'options': [{'value': c.id, 'label': c.display_name,
                             'count': okved_counts.get(c.id, 0)}
                            for c in classes if okved_counts.get(c.id)],
            })

        Group = self.env['coop.legal.form.group'].sudo()
        group_counts = counts('coop_legal_form_group_id',
                              without('coop_legal_form_group_id', 'coop_legal_form_id',
                                      'coop_cooperative_kind'))
        blocks.append({
            'code': 'group', 'label': 'Тип',
            'hint': 'Коммерческие, кооперативные, некоммерческие, '
                    'децентрализованные. ООО, АО и ИП — разновидности '
                    'коммерческих, а не отдельные типы.',
            'widget': 'select', 'field': 'coop_legal_form_group_id',
            'operator': '=', 'placeholder': 'Любой', 'counted': True,
            'reload': True,
            'options': [{'value': g.id, 'label': g.name,
                         'count': group_counts.get(g.id, 0)}
                        for g in Group.search([])],
        })
        group = chosen('coop_legal_form_group_id')
        if group:
            group = Group.browse(int(group)).exists()
        if group:
            form_counts = counts('coop_legal_form_id', without('coop_legal_form_id'))
            forms = self.env['coop.legal.form'].sudo().search(
                [('group_id', '=', group.id)])
            blocks.append({
                'code': 'form', 'label': 'Форма',
                'widget': 'select', 'field': 'coop_legal_form_id',
                'operator': '=', 'placeholder': 'Любая', 'counted': True,
                'options': [{'value': f.id, 'label': f.short_name or f.name,
                             'count': form_counts.get(f.id, 0)}
                            for f in forms if form_counts.get(f.id)],
            })
            if group.code == 'cooperative':
                kind_counts = counts('coop_cooperative_kind',
                                     without('coop_cooperative_kind'))
                kinds = self._fields['coop_cooperative_kind'].selection
                blocks.append({
                    'code': 'coop_kind', 'label': 'Вид кооператива',
                    'hint': 'От вида зависят правила: союзы и лимит выплат, '
                            'ревизионный союз, СРО, трудовое участие.',
                    'widget': 'select', 'field': 'coop_cooperative_kind',
                    'operator': '=', 'placeholder': 'Любой', 'counted': True,
                    'options': [{'value': code, 'label': label,
                                 'count': kind_counts.get(code, 0)}
                                for code, label in kinds if kind_counts.get(code)],
                })

        cities = sorted(c for c in counts('city', base) if c)
        blocks.append({
            'code': 'city', 'label': 'Город',
            'hint': 'Показать организации только из выбранного города.',
            'widget': 'text', 'field': 'city', 'operator': 'ilike',
            'placeholder': 'Начните вводить город',
            'options': [{'value': c, 'label': c} for c in cities],
        })

        trust_base = without('coop_trust')
        blocks.append({
            'code': 'trust', 'label': 'Уровень доверия',
            'hint': 'Двусторонние отзывы после сделок, хранятся в блокчейне '
                    'и неизменны.',
            'widget': 'select', 'field': 'coop_trust', 'operator': '>=',
            'number': True, 'placeholder': 'Любой', 'counted': True,
            'options': [{'value': step, 'label': f'От {step}%',
                         'count': orgs.search_count(
                             trust_base + [('coop_trust', '>=', step)])}
                        for step in self._COOP_ORG_TRUST_STEPS],
        })
        return blocks

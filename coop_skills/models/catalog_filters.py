# -*- coding: utf-8 -*-
from odoo import models


class CoopSkillOffer(models.Model):
    """Панель фильтров каталога навыков.

    Её не было ни в одной линии: справа стояло «пока отбирают порядком и
    поиском по названию» (владелец 12.10.2026: «почему у навыков нет
    фильтров?»). Набор — по макету `skills.html`: город, специализация с
    подкатегорией, опыт работы.
    """
    _inherit = 'coop.skill.offer'

    def _coop_catalog_filters(self, domain):
        def chosen(field):
            return next((leaf[2] for leaf in domain or []
                         if isinstance(leaf, (list, tuple)) and len(leaf) == 3
                         and leaf[0] == field), None)

        blocks = [{
            'code': 'city', 'label': 'Город',
            'hint': 'Показать навыки только из выбранного города.',
            'widget': 'text', 'field': 'city', 'operator': 'ilike',
            'placeholder': 'Начните вводить город',
        }]
        categories = self.env['coop.specialization.category'].sudo().search([])
        blocks.append({
            'code': 'category', 'label': 'Специализация',
            'hint': 'Профессиональная область.',
            'widget': 'select', 'field': 'coop_specialization_category_id',
            'operator': '=', 'number': True, 'placeholder': 'Любая', 'reload': True,
            'options': [{'value': c.id, 'label': c.name} for c in categories],
        })
        category = chosen('coop_specialization_category_id')
        specs = self.env['coop.specialization'].sudo().search(
            [('category_id', '=', int(category))]) if category else []
        # Сфера из одной специализации — бывший «Рабочий персонал»
        # (владелец 24.09.2026): «Сварщик» → «Сварщик». Выбирать там
        # нечего, и второй список читается как повтор.
        if len(specs) > 1:
            blocks.append({
                'code': 'spec', 'label': 'Подкатегория',
                'widget': 'select', 'field': 'coop_specialization_id',
                'operator': '=', 'number': True, 'placeholder': 'Любая',
                'options': [{'value': s.id, 'label': s.name} for s in specs],
            })
        blocks.append({
            'code': 'experience', 'label': 'Опыт работы',
            'hint': 'Общий стаж по этой специализации.',
            'widget': 'select', 'field': 'experience_level', 'operator': '=',
            'placeholder': 'Любой',
            'options': [{'value': code, 'label': label}
                        for code, label in self._fields['experience_level'].selection],
        })
        return blocks

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoopVacancy(models.Model):
    """Панель фильтров каталога вакансий.

    Её не было вовсе: справа стояло «пока отбирают порядком и поиском по
    названию» (находка 28.09.2026; решение 433, п. 18 — «чинить»). Набор —
    по макету `vacancies.html`: специализация с подкатегорией, кто ищет,
    город, занятость, опыт, вознаграждение.
    """
    _inherit = 'coop.vacancy'

    # «Кто ищет» из макета — организация, проект или частное лицо. Поле
    # «Кто нанимает» (`employer_kind`) отвечает на другой вопрос — ДАО,
    # артель, кооператив — и не хранится, а по невычисляемому не отобрать.
    seeker_kind = fields.Selection([
        ('org', 'Организация'),
        ('project', 'Проект'),
        ('person', 'Частное лицо'),
    ], string='Кто ищет (вид)', compute='_compute_seeker_kind', store=True, index=True)

    @api.depends('project_id', 'partner_id.is_company')
    def _compute_seeker_kind(self):
        for vacancy in self:
            if vacancy.project_id:
                vacancy.seeker_kind = 'project'
            elif vacancy.partner_id.is_company:
                vacancy.seeker_kind = 'org'
            else:
                vacancy.seeker_kind = 'person'

    def _coop_catalog_filters(self, domain):
        def chosen(field):
            return next((leaf[2] for leaf in domain or []
                         if isinstance(leaf, (list, tuple)) and len(leaf) == 3
                         and leaf[0] == field), None)

        def selection(field):
            return [{'value': code, 'label': label}
                    for code, label in self._fields[field].selection]

        def terms(kind):
            return [{'value': t.id, 'label': t.name}
                    for t in self.env['coop.vacancy.term'].sudo().search(
                        [('kind', '=', kind)])]

        categories = self.env['coop.specialization.category'].sudo().search([])
        blocks = [{
            'code': 'category', 'label': 'Специализация',
            'hint': 'Сфера деятельности — как в каталоге навыков.',
            'widget': 'select', 'field': 'coop_specialization_category_id',
            'operator': '=', 'number': True, 'placeholder': 'Любая', 'reload': True,
            'options': [{'value': c.id, 'label': c.name} for c in categories],
        }]
        category = chosen('coop_specialization_category_id')
        specs = self.env['coop.specialization'].sudo()
        if category:
            specs = specs.search([('category_id', '=', int(category))])
        # Сфера из одной специализации («Сварщик» → «Сварщик») — второй
        # список читается как повтор, как было в навыках (№ 278).
        if category and len(specs) > 1:
            blocks.append({
                'code': 'spec', 'label': 'Подкатегория',
                'widget': 'select', 'field': 'coop_specialization_id',
                'operator': '=', 'number': True, 'placeholder': 'Любая', 'reload': True,
                'options': [{'value': s.id, 'label': s.name} for s in specs],
            })
        blocks += [
            {'code': 'seeker', 'label': 'Кто ищет',
             'hint': 'Организация, проект или частное лицо.',
             'widget': 'select', 'field': 'seeker_kind', 'operator': '=',
             'placeholder': 'Любой', 'options': selection('seeker_kind')},
            {'code': 'city', 'label': 'Город',
             'hint': 'Показать вакансии только из выбранного города.',
             'widget': 'text', 'field': 'city', 'operator': 'ilike',
             'placeholder': 'Начните вводить город'},
            {'code': 'employment', 'label': 'Занятость',
             'widget': 'select', 'field': 'employment', 'operator': '=',
             'placeholder': 'Любая', 'options': selection('employment')},
            {'code': 'experience', 'label': 'Опыт работы',
             'widget': 'select', 'field': 'experience_level', 'operator': '=',
             'placeholder': 'Любой', 'options': selection('experience_level')},
            {'code': 'work_schedule', 'label': 'График',
             'widget': 'select', 'field': 'work_schedule', 'operator': '=',
             'placeholder': 'Любой', 'options': selection('work_schedule')},
            {'code': 'work_format', 'label': 'Формат работы',
             'widget': 'select', 'field': 'work_format', 'operator': '=',
             'placeholder': 'Любой', 'options': selection('work_format')},
            {'code': 'pay', 'label': 'Оплата от', 'unit': '₽',
             'hint': 'Пустое поле — без ограничения.',
             'widget': 'range', 'field': 'pay_from'},
            {'code': 'pay_frequency', 'label': 'Частота выплат',
             'widget': 'select', 'field': 'pay_frequency', 'operator': '=',
             'placeholder': 'Любая', 'options': selection('pay_frequency')},
            {'code': 'benefit', 'label': 'Что получают работники',
             'widget': 'select', 'field': 'benefit_ids', 'operator': '=',
             'number': True, 'placeholder': 'Любое',
             'options': terms('benefit')},
            {'code': 'audience', 'label': 'Подходит для',
             'widget': 'select', 'field': 'audience_ids', 'operator': '=',
             'number': True, 'placeholder': 'Любого',
             'options': terms('audience')},
            {'code': 'reward', 'label': 'Вознаграждение',
             'hint': 'Деньги, доля в проекте, обмен услугами или волонтёрство.',
             'widget': 'select', 'field': 'reward_kind', 'operator': '=',
             'placeholder': 'Любое', 'options': selection('reward_kind')},
        ]

        # Поля профессии — когда специализация определена: выбрана сама
        # или в сфере она одна.
        chosen_spec = chosen('coop_specialization_id')
        spec = (specs.browse(int(chosen_spec)).exists() if chosen_spec
                else specs if len(specs) == 1 else specs.browse())
        if spec:
            blocks = self._coop_attr_merge(blocks, self._coop_attr_blocks(
                domain, spec.attribute_definition))
        return blocks

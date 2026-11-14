# -*- coding: utf-8 -*-
"""Каталог «Управления проектами» в виде каталога платформы.

Действие открывало штатный канбан движка: свои карточки, свой
переключатель, без панели отбора справа и без карты (владелец 14.11.2026:
«те же виды, что в каталоге проектов»). Виды теперь общие —
`coop_catalog_kanban`, а модели для них нужны две вещи: город, по которому
рисуется карта и отбирает панель, и описание самой панели.
"""
from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # Город хранимый: карта каталога считает метки группировкой на
    # сервере, а группировать по вычисляемому без хранения Odoo не умеет.
    # Источник — сбор, из которого вырос проект; иначе уже назначенный
    # (миграция 20.0.1.3.21 дала город всем проектам); иначе заказчик.
    city = fields.Char(
        string='Город', compute='_compute_city', store=True, readonly=False,
        index=True)

    @api.depends('coop_project_id.city', 'partner_id.city')
    def _compute_city(self):
        for project in self:
            project.city = (project.coop_project_id[:1].city or project.city
                            or project.partner_id.city or False)

    def _coop_catalog_filters(self, domain):
        base = list(self.env.context.get('coop_base_domain') or [])

        def without(*fields_):
            return base + [leaf for leaf in domain or []
                           if not (isinstance(leaf, (list, tuple)) and leaf
                                   and leaf[0] in fields_)]

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

        status_counts = counts('last_update_status', without('last_update_status'))
        blocks.append({
            'code': 'status', 'label': 'Ход проекта',
            'hint': 'По последнему отчёту о ходе: идёт по плану, есть риск, '
                    'отстаёт, приостановлен или завершён.',
            'widget': 'select', 'field': 'last_update_status', 'operator': '=',
            'placeholder': 'Любой', 'counted': True,
            # «Установить статус» — призыв на кнопке движка, а в отборе
            # это проекты без единого отчёта о ходе.
            'options': [{'value': code,
                         'label': 'Без отчёта' if code == 'to_define' else label,
                         'count': status_counts.get(code, 0)}
                        for code, label in self._fields['last_update_status']
                        ._description_selection(self.env)
                        if status_counts.get(code)],
        })


        today = fields.Date.context_today(self)
        deadline_base = without('date')
        blocks.append({
            'code': 'deadline', 'label': 'Срок',
            'hint': 'Дата окончания проекта.',
            'widget': 'select', 'field': 'date', 'operator': '<',
            'placeholder': 'Любой', 'counted': True,
            'options': [{'value': str(today), 'label': 'Срок прошёл',
                         'count': self.search_count(
                             deadline_base + [('date', '<', today)])}],
        })
        return blocks

# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.fields import Domain

# Тип проекта — по тому, чем собирают (владелец 19.11.2026: подразделы
# «Проектов» — краудресурсинг, краудфандинг, краудсорсинг, волонтёрство;
# «в каталог проектов… в фильтр добавить тип проекта»). Один проект может
# быть сразу нескольких типов: собирает вклад и ставит задачи за токены.
PROJECT_TYPES = [
    ('crowdresourcing', 'Краудресурсинг'),
    # Владелец 19.11.2026: пункт «Краудинвестинг» после «Краудресурсинга»,
    # раздел в разработке, и в фильтр «Тип проекта».
    ('crowdinvesting', 'Краудинвестинг'),
    ('crowdfunding', 'Краудфандинг'),
    ('crowdsourcing', 'Краудсорсинг'),
    ('volunteering', 'Волонтёрство'),
]

# Чьи проекты считаются «моими» — то же условие, что у «Я инициатор».
INITIATOR_DOMAIN = ['|', ('partner_id.user_ids', 'in', 'UID'),
                    '&', ('author_id.user_ids', 'in', 'UID'),
                    ('partner_id.is_company', '=', True)]


class CoopProjectType(models.Model):
    _inherit = 'coop.project'

    coop_type = fields.Selection(
        PROJECT_TYPES, string='Тип проекта',
        compute='_compute_coop_type', search='_search_coop_type',
        help='Чем проект собирает: вкладом любыми ресурсами, инвестициями, деньгами, '
             'задачами за токены или помощью волонтёров.')

    def _coop_type_domain(self, code):
        """Условие типа. Краудресурсинг — у проекта есть потребности:
        вклад трудом, техникой, материалами, деньгами (решение 183).
        Краудсорсинг дописывает `coop_bounty`. Краудинвестинг, краудфандинг
        и волонтёрство в разработке — проектов этих типов пока нет."""
        if code == 'crowdresourcing':
            return [('need_ids', '!=', False)]
        return [('id', '=', 0)]

    def _compute_coop_type(self):
        for project in self:
            project.coop_type = next(
                (code for code, _label in PROJECT_TYPES
                 if project.filtered_domain(self._coop_type_domain(code))),
                False)

    def _search_coop_type(self, operator, value):
        # Odoo 19+ приводит «=» к «in»; «not in» движок строит отрицанием.
        if operator != 'in':
            return NotImplemented
        return Domain.OR([self._coop_type_domain(code)
                          for code in value if code] or [[('id', '=', 0)]])

    @api.model
    def coop_pm_visible(self, section):
        """Видна ли кнопка «Управление проектами» в подразделе: у человека
        есть свой проект этого подраздела (владелец 19.11.2026: «управление
        проектами у нас появляется кнопкой в том разделе где пользователь
        разместил проект, слева от добавить проект»)."""
        uid = self.env.uid
        mine = [(leaf[0], leaf[1], [uid]) if isinstance(leaf, tuple)
                and leaf[2] == 'UID' else leaf for leaf in INITIATOR_DOMAIN]
        domain = list(mine)
        if section in dict(PROJECT_TYPES):
            domain += [('coop_type', '=', section)]
        return bool(self.search_count(domain, limit=1))


class CoopProject(models.Model):
    """Панель фильтров каталога проектов.

    Её не было ни в одной линии: справа стояло «В этом разделе пока
    отбирают порядком и поиском по названию» (владелец 12.11.2026:
    «куда-то опять исчезли фильтры из каталога проектов»; «очень важно,
    чтобы были сделаны качественно все фильтры»). Набор — по макету
    `projects.html`: город, тема с разделом, готовность, экономическая
    модель; сверх макета — состояние сбора, которое было в штатном
    поиске, но до панели не доходило.
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

        # Тип проекта — вычисляемый, по группам не считается: счётчик —
        # поиском на каждый тип. Все типы видны всегда, и пустые — со
        # счётчиком 0 (владелец 19.11.2026: «все типы всегда»): по списку
        # видно, какие подразделы есть, даже если проектов в них пока нет.
        type_base = without('coop_type')
        type_counts = {code: self.search_count(type_base + [('coop_type', '=', code)])
                       for code, _label in PROJECT_TYPES}
        # В подразделе одного типа (краудресурсинг, краудсорсинг) отбор по
        # типу ничего не даёт — блок только в каталогах без типа.
        typed = any(isinstance(leaf, (list, tuple)) and leaf
                    and leaf[0] == 'coop_type' for leaf in base)
        blocks.append({
            'code': 'coop_type', 'label': 'Тип проекта',
            'hint': 'Чем проект собирает: вкладом любыми ресурсами, инвестициями, деньгами, '
                    'задачами за токены или помощью волонтёров.',
            'widget': 'select', 'field': 'coop_type', 'operator': '=',
            'placeholder': 'Любой', 'counted': True,
            'options': [{'value': code, 'label': label,
                         'count': type_counts[code]}
                        for code, label in PROJECT_TYPES],
        }) if not typed else None

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
        # «Срок на исходе» в панель не ставим (владелец 12.11.2026: «срок
        # на исходе убери»).
        return blocks

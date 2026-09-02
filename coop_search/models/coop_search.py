# -*- coding: utf-8 -*-
from odoo import api, models, _

# Что и где ищем. Порядок групп в выдаче — этот же: сначала люди и
# организации, потом то, что они предлагают, потом общее дело. Он не
# случайный: на платформе ищут прежде всего, с кем иметь дело.
#
# Каждая строка: модель, подпись группы, поля для поиска, домен видимого
# в каталоге, действие каталога.
SOURCES = [
    ('res.partner', 'Люди', ['name', 'city'],
     [('is_company', '=', False), ('coop_is_participant', '=', True)],
     'coop_people.action_coop_people'),
    ('res.partner', 'Организации', ['name', 'city'],
     [('is_company', '=', True), ('coop_is_participant', '=', True)],
     'coop_orgs.action_coop_orgs'),
    ('coop.community', 'Сообщества', ['name', 'summary', 'city'],
     [('state', '=', 'published')],
     'coop_communities.action_coop_communities'),
    ('coop.resource', 'Ресурсы', ['name', 'city'],
     [('state', '=', 'published')],
     'coop_resources.action_coop_resources'),
    ('coop.skill.offer', 'Навыки', ['name', 'city'],
     [('state', '=', 'published')],
     'coop_skills.action_coop_skills'),
    ('coop.vacancy', 'Вакансии', ['name', 'city'],
     [('state', '=', 'published')],
     'coop_vacancies.action_coop_vacancies'),
    ('coop.project', 'Проекты', ['name', 'summary', 'city'],
     [], 'coop_projects.action_coop_projects'),
]

# Сколько строк показываем в группе. Больше трёх — и выдача из семи
# разделов перестаёт читаться; ради полного списка есть «смотреть все».
PER_GROUP = 3
# Сколько групп показываем строками. Остальные сворачиваются в одну
# строку со счётчиками.
MAX_GROUPS = 4
# Ниже трёх символов не ищем: по одной букве совпадает половина базы, и
# человек получает список, из которого ничего не выбрать.
MIN_LENGTH = 3


class CoopSearch(models.AbstractModel):
    """Поиск по всем каталогам сразу.

    Отдельная модель, а не панель управления Odoo: та ищет по одной
    модели текущего действия, и приспособить её к межкаталожной выдаче
    значило бы подменить смысл фасетов.
    """

    _name = 'coop.search'
    _description = 'Поиск по платформе'

    @api.model
    def coop_lookup(self, term):
        term = (term or '').strip()
        if len(term) < MIN_LENGTH:
            return {'term': term, 'tooShort': True, 'groups': [], 'more': []}

        groups = []
        for model, label, fields_, domain, action_xmlid in SOURCES:
            if model not in self.env:
                continue
            groups.append(self._lookup_one(
                model, label, fields_, domain, action_xmlid, term))

        # Свои сделки — отдельной группой и всегда последними: чужая
        # сделка не объект публичного каталога, и мешать её с ресурсами
        # в одном списке нельзя.
        if 'coop.deal' in self.env:
            me = self.env.user.partner_id
            groups.append(self._lookup_one(
                'coop.deal', 'Мои сделки', ['name'],
                ['|', ('party_a_id', '=', me.id), ('party_b_id', '=', me.id)],
                'coop_deals.action_coop_deals', term, own=True))

        found = [g for g in groups if g['count']]
        return {
            'term': term,
            'tooShort': False,
            'groups': found[:MAX_GROUPS],
            'more': [{'label': g['label'], 'count': g['count'],
                      'action': g['action'], 'model': g['model']}
                     for g in found[MAX_GROUPS:]],
            'total': sum(g['count'] for g in found),
        }

    def _lookup_one(self, model, label, fields_, domain, action_xmlid, term,
                    own=False):
        """Одна группа выдачи.

        Считаем и выбираем раздельно: `search_count` по индексу дешевле,
        чем вытащить все записи ради длины списка.
        """
        Model = self.env[model]
        search = ['|'] * (len(fields_) - 1) + [
            (field, 'ilike', term) for field in fields_]
        full = list(domain) + search
        try:
            count = Model.search_count(full)
            records = Model.search(full, limit=PER_GROUP)
        except Exception:
            # Каталог может быть закрыт правами доступа — например,
            # пока не подтверждён профиль. Это не ошибка поиска.
            return {'model': model, 'label': label, 'count': 0,
                    'rows': [], 'action': action_xmlid, 'own': own}

        rows = []
        for record in records:
            rows.append({
                'id': record.id,
                'model': model,
                'name': record.display_name,
                'note': self._row_note(record),
            })
        return {'model': model, 'label': label, 'count': count, 'rows': rows,
                'action': action_xmlid, 'own': own}

    def _row_note(self, record):
        """Вторая строка результата — то, чем записи различают между собой."""
        parts = []
        city = getattr(record, 'city', False)
        if city:
            parts.append(city)
        summary = getattr(record, 'summary', False)
        if summary:
            parts.append(summary[:60])
        return ' · '.join(parts)

    @api.model
    def coop_open_catalog(self, action_xmlid, term):
        """Открыть каталог с этим же запросом в его собственном поиске."""
        action = self.env['ir.actions.act_window']._for_xml_id(action_xmlid)
        action['context'] = dict(action.get('context') or {},
                                 search_default_name=term)
        action['name'] = _('«%s» в разделе «%s»') % (term, action['name'])
        return action

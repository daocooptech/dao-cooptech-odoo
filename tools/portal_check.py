# -*- coding: utf-8 -*-
"""Обход портала: открывается ли каждый раздел, карточка, полка, кнопка.

Зачем. Владелец 21 сентября 2026: «проверь остальные разделы портала».
Открывать восемнадцать разделов руками — полчаса, и всё равно мимо
пройдёт то, что ломается не на первой карточке: кнопка без метода,
полка, открывающая окно вместо страницы, ссылка «смотреть все», которая
показывает не то же, что полка.

Что проверяется:

* раздел — действие разрешается, записи считаются, все виды собираются
  от имени участника (не администратора: у него другие права);
* карточка — форма собирается, видно, сколько полей правится по месту;
* полки страницы человека и карточки организации — число плиток против
  числа записей в «смотреть все», куда ведёт плитка и не окно ли это;
* кнопки — есть ли под каждой метод модели, к которой она относится
  (кнопка внутри встроенного списка зовёт метод строки, а не страницы);
* объём каталога — правило наполнения: сто-двести записей.

Запуск на боевой:

    sudo -u odoo /opt/coop/venv/bin/python /opt/coop/odoo/odoo-bin shell \\
        -c /etc/coop-odoo.conf -d koopeh --no-http < tools/portal_check.py
"""
import re

SECTIONS = [
    ('Люди', 'coop_people.action_coop_people'),
    ('Навыки', 'coop_skills.action_coop_skills'),
    ('Вакансии', 'coop_vacancies.action_coop_vacancies'),
    ('Ресурсы', 'coop_resources.action_coop_resources'),
    ('Проекты', 'coop_projects.action_coop_projects'),
    ('Организации', 'coop_orgs.action_coop_orgs'),
    ('Сообщества', 'coop_communities.action_coop_communities'),
    ('Кошелёк', 'coop_wallet.action_coop_my_wallet'),
    ('Сделки', 'coop_deals.action_coop_deals'),
    ('Токеномика', 'coop_tokenomics.action_coop_exchange_screen'),
    ('Цифровые активы', 'coop_digital_assets.action_coop_cfa_issue'),
    ('Нематериальные активы', 'coop_intangibles.action_coop_intangibles'),
    ('Целевые программы', 'coop_programs.action_coop_program'),
    ('Совместные закупки', 'coop_groupbuy.action_coop_groupbuy'),
    ('Аукционы', 'coop_auctions.action_coop_auction'),
    ('Склад', 'coop_warehouse.action_coop_warehouse_offer'),
    ('События', 'coop_events.action_coop_event'),
    ('Задания', 'coop_bounty.action_coop_bounty_task'),
]

PERSON_SHELVES = [
    ('Друзья', 'coop_friend_ids', 'action_coop_my_friends', None),
    ('Навыки', 'coop_offer_ids', 'action_coop_my_offers', None),
    ('Ресурсы', 'coop_resource_ids', 'action_coop_my_resources', None),
    ('Потребности', 'coop_need_ids', 'action_coop_my_needs', None),
    ('Вакансии', 'coop_vacancy_ids', 'action_coop_my_vacancies', None),
    ('Проекты', 'coop_project_ids', 'action_coop_my_projects', None),
    ('Организации', 'coop_active_membership_ids',
     'action_coop_my_organizations', None),
    ('Сообщества', 'coop_community_member_ids', 'action_coop_my_communities',
     [('state', '=', 'active')]),
]

ORG_SHELVES = [
    ('Состав', 'coop_member_ids', 'action_coop_members',
     [('state', '=', 'active')]),
    ('Ресурсы', 'coop_org_resource_ids', 'action_coop_org_resources', None),
    ('Проекты', 'coop_org_project_ids', 'action_coop_org_projects', None),
    ('Услуги', 'coop_org_service_ids', 'action_coop_org_services', None),
    ('Связанные', 'coop_related_org_ids', 'action_coop_org_related', None),
    ('Вакансии', 'coop_org_vacancy_ids', 'action_coop_org_vacancies', None),
    ('Потребности', 'coop_org_need_ids', 'action_coop_org_needs', None),
]

problems = []


def participant():
    """От чьего имени смотрим: обычный участник, а не администратор."""
    user = env['res.users'].sudo().search(
        [('partner_id.name', 'ilike', 'Дашкевич')], limit=1)
    return user or env['res.users'].sudo().search(
        [('share', '=', False), ('login', '!=', 'admin')], limit=1)


def sections(user):
    print('\n── Разделы ──────────────────────────────────────────────────')
    print('%-22s %-7s %-7s %-24s %-13s %s'
          % ('раздел', 'видно', 'всего', 'виды', 'карточка', 'по месту'))
    for title, xmlid in SECTIONS:
        try:
            action = env['ir.actions.actions'].sudo()._for_xml_id(xmlid)
        except Exception as error:
            print('%-22s %s' % (title, 'ДЕЙСТВИЯ НЕТ'))
            problems.append('%s: действия %s нет (%s)'
                        % (title, xmlid, str(error)[:60]))
            continue
        if action.get('type') == 'ir.actions.server':
            action = action  # серверное разрешается при нажатии
            model = (action.get('model_name')
                      or (action.get('model_id') and ''))
        model = action.get('res_model')
        if not model:
            print('%-22s свой экран' % title)
            continue
        domain = action.get('domain') or []
        if isinstance(domain, str):
            from odoo.tools.safe_eval import safe_eval
            domain = safe_eval(domain, {'uid': user.id})
        Model = env[model].with_user(user)
        how_many = Model.search_count(domain)
        # Сколько записей в каталоге всего. У сделок, кошелька и
        # переписки участник видит только своё — это правило доступа, а
        # не пустой каталог, и мерить наполнение по видимому значит
        # каждый раз объявлять бедой правильную работу прав.
        count_all = env[model].sudo().search_count(domain)
        bad, kinds = [], []
        for kind in (action.get('view_mode') or 'kanban,list,form').split(','):
            try:
                Model.get_views([(None, kind.strip())])
                kinds.append(kind.strip())
            except Exception as error:
                bad.append('%s: %s' % (kind, str(error)[:40]))
        card, by_place = '—', '—'
        if Model.search(domain, limit=1):
            try:
                is_collected = Model.get_views([(None, 'form')])
                arch = list(is_collected['views'].values())[0]['arch']
                by_place = arch.count('coop_inline') + arch.count('coop_block')
                card = 'открывается'
            except Exception as error:
                card = 'ОШИБКА'
                problems.append('%s: карточка — %s' % (title, str(error)[:60]))
        if bad:
            problems.append('%s: виды — %s' % (title, '; '.join(bad)))
        if count_all < 100:
            problems.append('%s: записей всего %s — меньше сотни' % (title, count_all))
        print('%-22s %-7s %-7s %-24s %-13s %s'
              % (title, how_many, count_all, ','.join(kinds), card, by_place))


def shelves(record, items, heading):
    print('\n── Полки: %s ──' % heading)
    print('%-14s %-7s %-28s %-8s %s'
          % ('полка', 'плиток', 'плитка ведёт на', 'в списке', 'заголовок'))
    for title, field, action, picked in items:
        records = record[field] if field in record._fields else record.browse()
        if picked:
            records = records.filtered_domain(picked)
        to_where = '—'
        if records and hasattr(records[0], 'action_coop_open_page'):
            transition = (records[0].action_coop_open_person
                       if field == 'coop_member_ids'
                       and hasattr(records[0], 'action_coop_open_person')
                       else records[0].action_coop_open_page)
            window = transition()
            to_where = '%s #%s' % (window.get('res_model'), window.get('res_id'))
            if window.get('target') == 'new':
                to_where += ' ОКНО!'
                problems.append('%s/%s: плитка открывает окно' % (heading, title))
        how_many, name = '—', 'ССЫЛКИ НЕТ'
        if action:
            screen = getattr(record, action)()
            name = screen.get('name') or '—'
            how_many = env[screen['res_model']].sudo().search_count(
                screen.get('domain') or [])
            if how_many != len(records):
                problems.append('%s/%s: полка %s, список %s'
                            % (heading, title, len(records), how_many))
        print('%-14s %-7s %-28s %-8s %s'
              % (title, len(records), to_where, how_many, name[:40]))


def buttons():
    """Есть ли под каждой кнопкой метод той модели, к которой она относится."""
    Kind = env['ir.ui.view'].sudo()
    kinds = Kind.search([('type', '=', 'form')]).filtered(
        lambda att: (att.model or '').startswith('coop.')
        or (att.model == 'res.partner' and 'coop' in (att.name or '')))
    checked = 0
    for kind in kinds:
        if kind.model not in env:
            continue
        arch = kind.arch or ''
        for found in re.finditer(
                r'<button[^>]*name="([a-z_0-9]+)"[^>]*type="object"', arch):
            checked += 1
            model = _button_model(arch, found.start(), kind.model)
            if model not in env or not hasattr(env[model], found.group(1)):
                problems.append('кнопка %s.%s (%s) — метода нет'
                            % (model, found.group(1), kind.name))
    print('\n── Кнопки ── проверено %s' % checked)


def _button_model(arch, position, form_model):
    chunk = arch[:position]
    nearest = form_model
    for field in re.finditer(r'<field name="([a-z_0-9]+)"[^>]*?([/]?)>', chunk):
        if field.group(2) == '/':
            continue
        if chunk.find('</field>', field.end()) == -1:
            description = env[form_model]._fields.get(field.group(1))
            if description is not None and description.relational:
                nearest = description.comodel_name
    return nearest


user = participant()
print('обход портала от имени: %s' % user.name)
sections(user)
me = user.partner_id
shelves(me, PERSON_SHELVES, 'страница человека')
org = env['res.partner'].sudo().search(
    [('is_company', '=', True), ('coop_is_participant', '=', True)],
    order='id', limit=1)
shelves(org, ORG_SHELVES, 'карточка организации')
buttons()

print('\n══ Итог: бед %s' % len(problems))
for problem in problems:
    print('   %s' % problem)

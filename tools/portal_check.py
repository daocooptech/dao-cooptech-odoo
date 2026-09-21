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

РАЗДЕЛЫ = [
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

ПОЛКИ_ЧЕЛОВЕКА = [
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

ПОЛКИ_ОРГАНИЗАЦИИ = [
    ('Состав', 'coop_member_ids', 'action_coop_members',
     [('state', '=', 'active')]),
    ('Ресурсы', 'coop_org_resource_ids', 'action_coop_org_resources', None),
    ('Проекты', 'coop_org_project_ids', 'action_coop_org_projects', None),
    ('Услуги', 'coop_org_service_ids', 'action_coop_org_services', None),
    ('Связанные', 'coop_related_org_ids', 'action_coop_org_related', None),
    ('Вакансии', 'coop_org_vacancy_ids', 'action_coop_org_vacancies', None),
    ('Потребности', 'coop_org_need_ids', 'action_coop_org_needs', None),
]

беды = []


def участник():
    """От чьего имени смотрим: обычный участник, а не администратор."""
    пользователь = env['res.users'].sudo().search(
        [('partner_id.name', 'ilike', 'Дашкевич')], limit=1)
    return пользователь or env['res.users'].sudo().search(
        [('share', '=', False), ('login', '!=', 'admin')], limit=1)


def разделы(пользователь):
    print('\n── Разделы ──────────────────────────────────────────────────')
    print('%-22s %-7s %-7s %-24s %-13s %s'
          % ('раздел', 'видно', 'всего', 'виды', 'карточка', 'по месту'))
    for название, xmlid in РАЗДЕЛЫ:
        try:
            действие = env['ir.actions.actions'].sudo()._for_xml_id(xmlid)
        except Exception as ошибка:
            print('%-22s %s' % (название, 'ДЕЙСТВИЯ НЕТ'))
            беды.append('%s: действия %s нет (%s)'
                        % (название, xmlid, str(ошибка)[:60]))
            continue
        if действие.get('type') == 'ir.actions.server':
            действие = действие  # серверное разрешается при нажатии
            модель = (действие.get('model_name')
                      or (действие.get('model_id') and ''))
        модель = действие.get('res_model')
        if not модель:
            print('%-22s свой экран' % название)
            continue
        домен = действие.get('domain') or []
        if isinstance(домен, str):
            from odoo.tools.safe_eval import safe_eval
            домен = safe_eval(домен, {'uid': пользователь.id})
        Модель = env[модель].with_user(пользователь)
        сколько = Модель.search_count(домен)
        # Сколько записей в каталоге всего. У сделок, кошелька и
        # переписки участник видит только своё — это правило доступа, а
        # не пустой каталог, и мерить наполнение по видимому значит
        # каждый раз объявлять бедой правильную работу прав.
        всего = env[модель].sudo().search_count(домен)
        плохие, виды = [], []
        for вид in (действие.get('view_mode') or 'kanban,list,form').split(','):
            try:
                Модель.get_views([(None, вид.strip())])
                виды.append(вид.strip())
            except Exception as ошибка:
                плохие.append('%s: %s' % (вид, str(ошибка)[:40]))
        карточка, по_месту = '—', '—'
        if Модель.search(домен, limit=1):
            try:
                собрана = Модель.get_views([(None, 'form')])
                arch = list(собрана['views'].values())[0]['arch']
                по_месту = arch.count('coop_inline') + arch.count('coop_block')
                карточка = 'открывается'
            except Exception as ошибка:
                карточка = 'ОШИБКА'
                беды.append('%s: карточка — %s' % (название, str(ошибка)[:60]))
        if плохие:
            беды.append('%s: виды — %s' % (название, '; '.join(плохие)))
        if всего < 100:
            беды.append('%s: записей всего %s — меньше сотни' % (название, всего))
        print('%-22s %-7s %-7s %-24s %-13s %s'
              % (название, сколько, всего, ','.join(виды), карточка, по_месту))


def полки(запись, список, заголовок):
    print('\n── Полки: %s ──' % заголовок)
    print('%-14s %-7s %-28s %-8s %s'
          % ('полка', 'плиток', 'плитка ведёт на', 'в списке', 'заголовок'))
    for название, поле, действие, отбор in список:
        записи = запись[поле] if поле in запись._fields else запись.browse()
        if отбор:
            записи = записи.filtered_domain(отбор)
        куда = '—'
        if записи and hasattr(записи[0], 'action_coop_open_page'):
            переход = (записи[0].action_coop_open_person
                       if поле == 'coop_member_ids'
                       and hasattr(записи[0], 'action_coop_open_person')
                       else записи[0].action_coop_open_page)
            окно = переход()
            куда = '%s #%s' % (окно.get('res_model'), окно.get('res_id'))
            if окно.get('target') == 'new':
                куда += ' ОКНО!'
                беды.append('%s/%s: плитка открывает окно' % (заголовок, название))
        сколько, имя = '—', 'ССЫЛКИ НЕТ'
        if действие:
            экран = getattr(запись, действие)()
            имя = экран.get('name') or '—'
            сколько = env[экран['res_model']].sudo().search_count(
                экран.get('domain') or [])
            if сколько != len(записи):
                беды.append('%s/%s: полка %s, список %s'
                            % (заголовок, название, len(записи), сколько))
        print('%-14s %-7s %-28s %-8s %s'
              % (название, len(записи), куда, сколько, имя[:40]))


def кнопки():
    """Есть ли под каждой кнопкой метод той модели, к которой она относится."""
    Вид = env['ir.ui.view'].sudo()
    виды = Вид.search([('type', '=', 'form')]).filtered(
        lambda в: (в.model or '').startswith('coop.')
        or (в.model == 'res.partner' and 'coop' in (в.name or '')))
    проверено = 0
    for вид in виды:
        if вид.model not in env:
            continue
        arch = вид.arch or ''
        for найдено in re.finditer(
                r'<button[^>]*name="([a-z_0-9]+)"[^>]*type="object"', arch):
            проверено += 1
            модель = _модель_кнопки(arch, найдено.start(), вид.model)
            if модель not in env or not hasattr(env[модель], найдено.group(1)):
                беды.append('кнопка %s.%s (%s) — метода нет'
                            % (модель, найдено.group(1), вид.name))
    print('\n── Кнопки ── проверено %s' % проверено)


def _модель_кнопки(arch, позиция, модель_формы):
    кусок = arch[:позиция]
    ближайшая = модель_формы
    for поле in re.finditer(r'<field name="([a-z_0-9]+)"[^>]*?([/]?)>', кусок):
        if поле.group(2) == '/':
            continue
        if кусок.find('</field>', поле.end()) == -1:
            описание = env[модель_формы]._fields.get(поле.group(1))
            if описание is not None and описание.relational:
                ближайшая = описание.comodel_name
    return ближайшая


пользователь = участник()
print('обход портала от имени: %s' % пользователь.name)
разделы(пользователь)
я = пользователь.partner_id
полки(я, ПОЛКИ_ЧЕЛОВЕКА, 'страница человека')
орг = env['res.partner'].sudo().search(
    [('is_company', '=', True), ('coop_is_participant', '=', True)],
    order='id', limit=1)
полки(орг, ПОЛКИ_ОРГАНИЗАЦИИ, 'карточка организации')
кнопки()

print('\n══ Итог: бед %s' % len(беды))
for беда in беды:
    print('   %s' % беда)

# -*- coding: utf-8 -*-
"""Учётные записи участникам.

Каталог людей на триста с лишним человек, а учётных записей на платформе
было три. Последствие не в том, что «мало пользователей», а в том, что
**вторая сторона любого взаимодействия не может действовать**: у сделки
некому подтвердить акт, у вакансии некому ответить на отклик, у торга
некому перебить ставку. Проверка 15 сентября 2026 показала это прямо: из
527 сделок ни одной, где у второй стороны есть запись, — двусторонний
путь непроверяем в принципе.

Здесь участники становятся настоящими действующими лицами: у каждого
человека из каталога появляется учётная запись, привязанная к его
карточке. Пароль не назначается — вход настраивается отдельно; для
платформы важно, что у записей есть хозяин, от чьего имени работают
правила доступа и кому приходят извещения.

Организациям записи не заводятся: от лица организации действует человек,
которому она поручила дела, — это уже устроено полномочиями.
"""

import logging
import re

from odoo import _

_logger = logging.getLogger(__name__)

# Транслитерация по ГОСТ-подобной таблице: логин должен читаться, а не
# быть номером. «Беляева Вера Петровна» → `belyaeva-vp`.
TABLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def to_latin(text):
    return ''.join(TABLE.get(ch, ch if ch.isalnum() else '') for ch in (text or '').lower())


def login_for(name):
    """Фамилия и инициалы: `belyaeva-vp`."""
    parts = [part for part in re.split(r'\s+', (name or '').strip()) if part]
    if not parts:
        return ''
    surname = to_latin(parts[0])
    initials = ''.join(to_latin(part[0]) for part in parts[1:3])
    return '-'.join(filter(None, [surname, initials]))


def load_accounts(env):
    """Завести учётные записи участникам-людям."""
    Partner = env['res.partner'].sudo()
    Users = env['res.users'].sudo()

    group = env.ref('base.group_user', raise_if_not_found=False)
    if not group:
        _logger.warning('Учётные записи: нет группы base.group_user')
        return 0

    # Только люди и только те, кто состоит хоть в одной организации или
    # имеет специализацию: в справочнике есть и технические карточки, и
    # контрагенты без отношения к платформе.
    participants = Partner.search([
        ('is_company', '=', False),
        ('user_ids', '=', False),
        '|', ('coop_specialization_id', '!=', False),
        ('id', 'in', env['coop.membership'].sudo().search([]).mapped(
            'partner_id').ids),
    ])

    taken_list = set(Users.with_context(active_test=False).search([]).mapped('login'))
    created = 0
    for partner in participants:
        base = login_for(partner.name)
        if not base:
            base = 'uchastnik-%s' % partner.id
        login, number = base, 1
        # Однофамильцы с одинаковыми инициалами в каталоге есть, и
        # второй такой же логин упал бы на ограничении уникальности,
        # оборвав загрузку на середине.
        while login in taken_list:
            number += 1
            login = '%s-%s' % (base, number)
        taken_list.add(login)
        try:
            Users.create({
                'login': login,
                'partner_id': partner.id,
                'group_ids': [(6, 0, [group.id])],
            })
            created += 1
        except Exception as error:  # noqa: BLE001
            # Одна карточка не должна ронять загрузку остальных трёхсот.
            _logger.warning('Учётные записи: %s — %s', partner.name, error)

    _logger.info('Учётные записи: заведено %s, всего участников %s',
                 created, len(participants))
    return created

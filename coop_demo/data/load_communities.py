# -*- coding: utf-8 -*-
"""Каталог сообществ из макета — и состав к нему.

Сто карточек взяты из `communities.html`, ещё двадцать восемь дописаны:
в выгрузке «финансовых» и «локальных» сообществ было по одному, и
фильтр по этим типам показывал единственную запись — на такой выборке
не видно ни группировки, ни постраничной навигации.

Число участников в макете стоит полем и взято с потолка: у «Фермеров —
Тобольск» их 832. Здесь оно не переносится, а задаёт, сколько людей
завести в состав — счётчик на карточке считается из состава. Иначе
первый же клик по «Участники» показывает четверых против восьмисот на
плитке, и доверие к цифрам платформы кончается на этом экране.

Состав кладётся не только из принятых: заявки на рассмотрении,
отклонённые, вышедшие и исключённые — это разные состояния экрана, и
без них модерация не проверяется.
"""
import base64
import io
import json
import logging
import os
import random

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'projects')

KIND = {
    'Соседское': 'neighbourhood',
    'По интересам': 'interest',
    'Профессиональное': 'professional',
    'Финансовое': 'financial',
    'Локальное': 'local',
}

# Снимок к сообществу подбирается по теме — по той же причине, по
# которой он подбирается по названию у проектов: на плитке видно именно
# фотографию, и «Пасечники» с кадром стройки читаются как сбой загрузки.
PHOTOS_BY_KIND = {
    'neighbourhood': ['community-meeting.jpg', 'playground.jpg', 'outdoor-library.jpg'],
    'interest': ['climbing-gym.jpg', 'bicycle-repair.jpg', 'apple-orchard.jpg',
                 'craft-workshop.jpg'],
    'professional': ['makerspace.jpg', 'carpentry-shop.jpg', 'weaving-loom.jpg',
                     'cheese-making.jpg', 'apiary-hives.jpg', 'sewing-workshop.jpg',
                     'bakery-bread.jpg', 'milk-tank.jpg'],
    'financial': ['toolbox.jpg', 'office-desk.jpg'],
    'local': ['community-meeting.jpg', 'coworking.jpg'],
}

# Каким по счёту сообществам какой порог входа. Открытых большинство:
# закрытая группа — исключение, а не норма, и если сделать наоборот,
# каталог превращается в список запертых дверей.
ACCESS_BY_INDEX = (
    ['public'] * 7 + ['request'] * 2 + ['closed']
)

# Состояния участия в составе. Принятых подавляющее большинство —
# остальное нужно, чтобы было на чём проверить модерацию.
MEMBER_STATES = (
    ['active'] * 14 + ['pending', 'pending', 'left', 'rejected', 'banned', 'active']
)

REJECTION_REASONS = [
    'Сообщество для жителей района, заявитель из другого города.',
    'Нет подтверждённого контакта — написать в случае спора некуда.',
    'Профиль пустой: непонятно, чем человек может быть полезен группе.',
    'Заявка дублирует поданную неделю назад.',
]

BAN_REASONS = [
    'Реклама сторонних услуг в обсуждении после двух предупреждений.',
    'Не рассчитался по совместной закупке, вопрос вынесен в спор.',
    'Оскорбления в адрес участников на встрече и в переписке.',
]

APPLICATION_NOTES = [
    'Живу в соседнем доме, хочу участвовать в закупках.',
    'Держу небольшое хозяйство, могу делиться излишками.',
    'Работаю по этому ремеслу восемь лет, готов наставничать.',
    'Ищу, с кем скинуться на технику — в одиночку не тяну.',
    'Переехал недавно, хочу познакомиться с соседями.',
]


def load_communities(env):
    """Завести сообщества, их состав и связи с проектами."""
    path = os.path.join(HERE, 'communities.json')
    rows = json.load(io.open(path, encoding='utf-8'))

    Community = env['coop.community'].sudo()
    Member = env['coop.community.member'].sudo()
    Partner = env['res.partner'].sudo()

    people = Partner.search([
        ('is_company', '=', False),
        ('coop_is_participant', '=', True),
    ], order='id')
    if not people:
        _logger.warning('Сообщества: не найдено ни одного человека, пропускаю')
        return 0

    companies = Partner.search([
        ('is_company', '=', True),
        ('coop_is_participant', '=', True),
    ], order='id')
    projects = env['coop.project'].sudo().search([], limit=60, order='id')

    rnd = random.Random(4711)
    created = updated = 0

    for index, row in enumerate(rows):
        key = 'communities.json#%s' % index
        kind = KIND[row['kind']]
        # Владелец — человек, а для профессиональных иногда организация:
        # в макете «Дербентские овцеводы» держит кооператив.
        if companies and kind == 'professional' and index % 5 == 2:
            owner = companies[index % len(companies)]
        else:
            owner = people[(index * 3) % len(people)]

        values = {
            'name': row['name'],
            'summary': row['description'],
            'description': '<p>%s</p>' % row['description'],
            'rules': _rules_for(kind),
            'kind': kind,
            'city': row['city'],
            'icon': row['icon'],
            'access': ACCESS_BY_INDEX[index % len(ACCESS_BY_INDEX)],
            'partner_id': owner.id,
            'import_key': key,
        }
        # Связь именная и единственная: либо проект, либо организация.
        if row['linked_page'] and projects:
            values['project_id'] = projects[index % len(projects)].id
        elif owner.is_company:
            values['organization_id'] = owner.id

        photos = PHOTOS_BY_KIND[kind]
        photo = os.path.join(PHOTO_DIR, photos[index % len(photos)])
        if os.path.exists(photo):
            with open(photo, 'rb') as handle:
                values['image_1920'] = base64.b64encode(handle.read())

        community = Community.search([('import_key', '=', key)], limit=1)
        if community:
            community.write(values)
            updated += 1
        else:
            community = Community.create(values)
            created += 1

        if not community.member_ids:
            # Каждое сообщество должно пережить ошибку в соседнем:
            # PostgreSQL обрывает транзакцию на первой же, и без точки
            # сохранения молча не создастся весь остаток каталога.
            with env.cr.savepoint():
                _make_members(env, Member, community, owner, people, row, rnd, index)

        # Канал заводится здесь, а не вызовом action_publish: тот
        # требует у владельца подтверждённый контакт, а половина
        # демонстрационных участников до этой ступени намеренно не
        # доведена — иначе не на чем показать ограничения.
        if not community.channel_id:
            community.channel_id = community._create_channel()

        # Закрытых и замороженных немного, но они должны быть: на них
        # проверяются приглушённая плитка и запрет на вступление.
        if index % 23 == 7:
            community.state = 'archived'
        elif index % 31 == 11:
            community.state = 'frozen'
        else:
            community.state = 'published'
        community.member_ids._sync_channel()

    _logger.info('Сообщества: создано %s, обновлено %s', created, updated)
    return created + updated


def _rules_for(kind):
    """Правила группы — то, с чем человек соглашается при вступлении."""
    common = ('Здесь договариваются о деле, а не выясняют отношения. '
              'Реклама сторонних услуг — только в закреплённой теме.')
    extra = {
        'neighbourhood': 'Участвуют жители района. Вещи передаём из рук в руки.',
        'professional': 'Совет по ремеслу даём по опыту, а не по слухам.',
        'financial': 'Условия займа и возврата фиксируются до передачи денег.',
        'interest': 'Снаряжение и инструмент возвращаем в том виде, в каком взяли.',
        'local': 'Вопросы новичков не считаются глупыми — на них отвечают.',
    }
    return '%s %s' % (extra.get(kind, ''), common)


def _make_members(env, Member, community, owner, people, row, rnd, index):
    """Завести состав по числу участников из макета."""
    # Ведущий заводится первым: без него сообщество нельзя опубликовать.
    Member.create({
        'community_id': community.id,
        'partner_id': owner.id,
        'role': 'owner',
        'state': 'active',
        'joined_on': '2025-%02d-%02d' % (1 + index % 12, 1 + index % 27),
    })

    # Сотни участников в базу не кладём — кладём столько, чтобы хватило
    # на списки, фильтры и постраничную навигацию. Счётчик на карточке
    # честный: он считается из того, что реально заведено.
    target = max(4, min(28, row['members'] // 12))
    taken = {owner.id}
    for step in range(target):
        person = people[(index * 7 + step * 13) % len(people)]
        if person.id in taken:
            continue
        taken.add(person.id)

        state = MEMBER_STATES[(index + step) % len(MEMBER_STATES)]
        values = {
            'community_id': community.id,
            'partner_id': person.id,
            'state': state,
            # Модератором становится каждый девятый принятый: один
            # ведущий на сообщество с тремя сотнями участников — это
            # заявка, которую некому разобрать.
            'role': 'moderator' if state == 'active' and step % 9 == 4 else 'member',
        }
        if state == 'pending':
            values['applied_on'] = '2026-08-%02d 09:%02d:00' % (
                1 + (index + step) % 28, (index * 7 + step) % 60)
            values['application_note'] = APPLICATION_NOTES[
                (index + step) % len(APPLICATION_NOTES)]
        else:
            values['joined_on'] = '2025-%02d-%02d' % (
                1 + (index + step) % 12, 1 + (index * 3 + step) % 27)
        if state == 'rejected':
            values['decision_reason'] = REJECTION_REASONS[
                (index + step) % len(REJECTION_REASONS)]
            values['decided_on'] = '2026-07-%02d 12:00:00' % (1 + (index + step) % 28)
        if state == 'banned':
            values['decision_reason'] = BAN_REASONS[(index + step) % len(BAN_REASONS)]
            values['decided_on'] = '2026-06-%02d 12:00:00' % (1 + (index + step) % 28)
            values['left_on'] = '2026-06-%02d' % (1 + (index + step) % 28)
        if state == 'left':
            values['left_on'] = '2026-%02d-%02d' % (1 + (index + step) % 8,
                                                    1 + (index + step) % 27)
        Member.create(values)

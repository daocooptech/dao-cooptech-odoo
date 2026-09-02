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

# Снимок лежит в самих данных и подобран по названию, а не по типу
# сообщества. Типов пять, названий два десятка: подбор по типу дал на
# плитке «Айтишников» с коровником и «Дачников» с сараем — ровно ту же
# болезнь, что была у проектов, только через другую дверь.

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

# По каким словам искать проект, к которому сообщество привязано.
# Раньше проект брался по порядковому номеру, и «Столяры» оказывались
# при «Сыроварне кооператива»: связь на карточке видна строкой, и такая
# пара читается как ошибка загрузки. Не нашлось подходящего — связи
# просто нет, это честнее выдуманной.
PROJECT_WORDS = {
    'Айтишники': ['CRM', 'программирован'],
    'Велосипедисты': ['ремонту техники', 'Ремонтная база'],
    'Волонтёры': ['Модульные дома', 'дома культуры'],
    'Дачники': ['теплиц', 'Питомник'],
    'Кузнецы': ['Кузнечная'],
    'Мастера': ['мастерская', 'FabLab'],
    'Овцеводы': ['шерст'],
    'Пасечники': ['Пасека'],
    'Пчеловоды': ['Пасека'],
    'Родители': ['площадка'],
    'Рыбаки': ['Рыбное'],
    'Садоводы': ['Питомник', 'теплиц'],
    'Соседи': ['баня', 'прачечная'],
    'Столяры': ['Модульный дом', 'мастерская по ремонту'],
    'Сыроделы': ['Сыроварня'],
    'Ткачи': ['Ткацкая'],
    'Фермеры': ['Мельница', 'Молочный', 'Тепличный'],
    'Строим вместе': ['3д принтер', 'Модульный дом'],
    'Огород и теплицы': ['теплиц'],
    'Мастера и рукоделие': ['Гончарная', 'мастерская'],
    'Дербентские овцеводы': ['шерст', 'Сыроварня'],
    'IT-кооператоры': ['CRM'],
}

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
    Project = env['coop.project'].sudo()

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
        # Обе связи выставляются явно, в том числе пустыми: иначе при
        # повторной заливке у сообщества остаётся привязка, поставленная
        # прошлой версией загрузчика, и правка не доезжает до стенда.
        # Сообщество организации так и подписано в макете («Сообщество
        # кооператива "Шукты"»), поэтому связь с организацией старше:
        # если группу держит юрлицо, показывать вместо этого проект
        # значит подменить владельца поводом.
        if owner.is_company:
            values['organization_id'] = owner.id
            values['project_id'] = False
        else:
            project = _project_for(Project, row['name'], row['city'])
            values['project_id'] = project.id if project else False
            values['organization_id'] = False

        photo = os.path.join(PHOTO_DIR, row['photo'])
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

        # Состав пересобирается, если он разошёлся с задуманным: иначе
        # правка загрузчика не доезжает до уже залитого стенда, и
        # проверять приходится на данных прошлой версии.
        if len(community.member_ids) != min(_member_target(row), len(people) - 1) + 1:
            # Пока состав перебирается, сообщество возвращается в
            # черновик: у опубликованного обязан быть ведущий, а он в
            # этот момент как раз удаляется.
            community.state = 'draft'
            community.member_ids.unlink()
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


def _project_for(Project, name, city):
    """Проект, к которому сообщество относится по смыслу, а не по счёту.

    При прочих равных берётся проект того же города: «Пасечники —
    Казань» при пасеке в Ярославле выглядят опечаткой, хотя формально
    тема совпадает.
    """
    key = name if name in PROJECT_WORDS else name.split(' — ')[0]
    for word in PROJECT_WORDS.get(key, []):
        same_city = Project.search(
            [('name', 'ilike', word), ('city', '=', city)], limit=1, order='id')
        if same_city:
            return same_city
    for word in PROJECT_WORDS.get(key, []):
        project = Project.search([('name', 'ilike', word)], limit=1, order='id')
        if project:
            return project
    return Project.browse()


def _member_target(row):
    """Сколько человек завести в состав.

    Число из макета взято с потолка — у «Фермеров — Тобольск» стояло 832
    участника, — поэтому оно не переносится, а только задаёт разброс.
    Без разброса на всех плитках стоит одно и то же число, и каталог
    читается как заполненный заглушкой.
    """
    return 3 + row['members'] % 26


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
    # честный: он считается из того, что реально заведено. Разброс
    # берётся из числа в макете: без него на всех плитках стояло одно и
    # то же «24», и каталог выглядел заполненным заглушкой.
    target = min(_member_target(row), len(people) - 1)
    taken = {owner.id}
    step = probe = 0
    # Идём, пока не наберём заданное число, а не заданное число шагов:
    # при простом переборе повторы выпадали из состава, и в базе
    # оказывалось меньше людей, чем задумано. Тогда загрузчик считал
    # состав разошедшимся и пересобирал его при каждом запуске.
    while step < target and probe < len(people) * 3:
        person = people[(index * 7 + probe * 13) % len(people)]
        probe += 1
        if person.id in taken:
            continue
        taken.add(person.id)
        step += 1

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

# -*- coding: utf-8 -*-
"""Наполнение каталога навыков из макета.

Сто предложений навыка из `skills.html`: чем человек занимается, за
сколько, с каким опытом и какими умениями.

Владельцы берутся по имени из макета — там они указаны у всех ста
карточек. Тех, кого в каталоге людей нет, заводить не нужно: имена в
макете взяты из того же списка участников, и расхождение означало бы
ошибку разбора, а не нового человека.
"""
import base64
import json
import logging
import os

from . import emblems, professions

_logger = logging.getLogger(__name__)

def _state_for(index):
    """Состояние предложения с разбросом.

    В наборе все записи были опубликованными, и проверить на нём
    приостановленное предложение или черновик было физически не на чем —
    а именно в этих состояниях экран и ломается. Доли небольшие: каталог
    должен оставаться каталогом, а не витриной состояний.
    """
    if index % 17 == 5:
        return 'paused'
    if index % 23 == 7:
        return 'draft'
    return 'published'


HERE = os.path.dirname(os.path.abspath(__file__))
PHOTO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img', 'skills')


def load_skills(env):
    with open(os.path.join(HERE, 'skills.json'), encoding='utf-8') as fh:
        rows = json.load(fh)

    Offer = env['coop.skill.offer'].sudo()
    Partner = env['res.partner'].sudo()
    Skill = env['hr.skill'].sudo()
    skill_type = env.ref('coop_demo.skill_type_craft')

    specializations = {s.name: s for s in env['coop.specialization'].sudo().search([])}
    skills = {s.name: s for s in Skill.search([])}
    people = Partner.search(
        [('coop_is_participant', '=', True), ('is_company', '=', False)], order='id')

    created = updated = missing_owner = 0

    # Фотография и описание по специализации — из макета. Достроенным
    # предложениям брать их неоткуда, а карточка без снимка и без текста
    # в каталоге выглядит как незаполненная форма, а не как предложение
    # мастера.
    photo_by_spec, texts_by_spec = {}, {}
    photo_by_area, texts_by_area = {}, {}
    for row in rows:
        spec = row['specialization']
        area = row['category']
        if row['photo']:
            name = os.path.basename(row['photo'])
            photo_by_spec.setdefault(spec, name)
            photo_by_area.setdefault(area, name)
        if row['description']:
            texts_by_spec.setdefault(spec, [])
            if row['description'] not in texts_by_spec[spec]:
                texts_by_spec[spec].append(row['description'])
            texts_by_area.setdefault(area, [])
            if row['description'] not in texts_by_area[area]:
                texts_by_area[area].append(row['description'])

    for index, row in enumerate(rows):
        owner = Partner.search(
            [('name', '=', row['owner']), ('is_company', '=', False)], limit=1)
        if not owner:
            # Владельца из макета нет в каталоге — берём по кругу, но
            # считаем: если таких много, значит разбор макета сломан.
            missing_owner += 1
            owner = people[index % len(people)] if people else None
        if not owner:
            continue

        # Умения из чипов карточки. Заводятся в том же типе, что и умения
        # людей: справочник один, и разводить его на «умения человека» и
        # «умения из предложения» значит немедленно получить два списка с
        # одинаковыми названиями.
        skill_ids = []
        for name in row['skills']:
            skill = skills.get(name)
            if not skill:
                skill = Skill.create({'name': name, 'skill_type_id': skill_type.id})
                skills[name] = skill
            skill_ids.append(skill.id)

        specialization = specializations.get(row['specialization'])
        values = {
            'name': row['name'],
            'description': '<p>%s</p>' % row['description'] if row['description'] else False,
            'partner_id': owner.id,
            'coop_specialization_id': specialization.id if specialization else False,
            'skill_ids': [(6, 0, skill_ids)],
            'city': row['city'],
            'ready_to_travel': row['travel'],
            'experience_months': row['experience_months'],
            'rate': row['rate'],
            'rate_kind': row['rate_kind'],
            'rate_period': row['rate_period'],
            'state': _state_for(index),
        }

        photo = os.path.join(PHOTO_DIR, os.path.basename(row['photo'])) if row['photo'] else ''
        if photo and os.path.exists(photo):
            with open(photo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read()).decode()

        # Опознаём по ключу источника, а не по названию: название
        # правится, и тогда загрузчик заводит запись заново вместо того,
        # чтобы поправить существующую.
        key = 'skills.json#%s' % index
        values['import_key'] = key
        existing = Offer.search([('import_key', '=', key)], limit=1)
        if existing:
            existing.write(values)
            updated += 1
        else:
            Offer.create(values)
            created += 1

    # Предложения остальным участникам. В макете сто карточек держат
    # семнадцать человек, а участников в каталоге сотня: такой перекос
    # читается как сбой данных, а не как живой каталог. Достраиваем по
    # собственной специализации и умениям человека — то есть по тому, что
    # он и так о себе заявил.
    generated = _generate_missing(env, Offer, Partner,
                                  photo_by_spec, texts_by_spec,
                                  photo_by_area, texts_by_area)
    filled = _fill_empty_specializations(env, Offer, Partner, Skill, skill_type)

    if missing_owner:
        _logger.warning('Каталог навыков: у %s предложений владелец из макета '
                        'не найден среди участников', missing_owner)
    _logger.info('Каталог навыков: из макета %s (создано %s, обновлено %s), '
                 'достроено по участникам %s, по пустым специализациям %s',
                 len(rows), created, updated, generated, filled)


# Ставка подбирается по специализации: сварщик и бухгалтер стоят
# по-разному, и одинаковая ставка у всех сделала бы фильтр по цене
# бессмысленным. Числа — порядок величины по рынку, не прайс-лист.
RATE_BY_AREA = {
    'Информационные технологии': 150000,
    'Финансы, бухгалтерия': 90000,
    'Юристы': 100000,
    'Строительство, недвижимость': 95000,
    'Медицина, фармацевтика': 75000,
    'Транспорт, логистика, перевозки': 80000,
    # Бывший «Рабочий персонал» — теперь сфера на каждую специальность
    # (24 сентября 2026); вилка прежняя.
    'Бетонщик, арматурщик, каменщик': 70000,
    'Кладовщик, Приемщик товаров': 70000,
    'Разнорабочий': 70000,
    'Сварщик': 70000,
    'Слесарь, сантехник': 70000,
    'Столяр, плотник': 70000,
    'Электромонтажник, электромонтер, техник-электрик': 70000,
    'Производство, сервисное обслуживание': 72000,
    'Сельское хозяйство': 60000,
    'Розничная торговля': 55000,
    'Домашний, обслуживающий персонал': 50000,
}
DEFAULT_RATE = 65000


def _generate_missing(env, Offer, Partner, photo_by_spec, texts_by_spec,
                      photo_by_area, texts_by_area):
    """Завести предложение каждому участнику, у которого его нет.

    Заголовок — название его специализации: человек, назвавшийся
    сварщиком, предлагает сварку. Умения берутся его собственные, ставка —
    по сфере деятельности с разбросом, опыт — из возраста, но не больше
    правдоподобного: сорокалетний электрик мог работать двадцать лет,
    двадцатилетний — нет.
    """
    people = Partner.search([
        ('coop_is_participant', '=', True), ('is_company', '=', False),
        ('coop_specialization_id', '!=', False),
    ])
    with_offer = set(Offer.search([]).mapped('partner_id').ids)

    created = 0
    for index, person in enumerate(people):
        if person.id in with_offer:
            continue

        specialization = person.coop_specialization_id
        area = specialization.category_id.name if specialization.category_id else ''
        base = RATE_BY_AREA.get(area, DEFAULT_RATE)
        # Разброс ±20% по номеру записи: одинаковые ставки в списке
        # выглядят как подставленное значение по умолчанию, каким они и
        # были бы.
        rate = int(base * (0.8 + (index % 9) * 0.05) / 1000) * 1000

        # Опыт: не больше числа лет с восемнадцати. Иначе в каталоге
        # появляется двадцатилетний мастер с пятнадцатью годами стажа.
        possible = max(0, (person.coop_age or 30) - 18)
        years = min(possible, 1 + (index % 12))
        months = (index * 7) % 12

        # Заголовок — первое занятие из перечня специализации.
        # «Электромонтажник, электромонтер, техник-электрик» целиком в
        # заголовке карточки не читается: это строка справочника, а не
        # то, как человек себя называет.
        title = specialization.name.split(',')[0].strip()

        # Описание: своё по специализации, иначе — соседнее по сфере
        # деятельности, иначе — собрано из умений человека. Пустое
        # описание в каталоге хуже общего: по нему не понять, берётся
        # человек за работу или просто числится.
        texts = (texts_by_spec.get(specialization.name)
                 or texts_by_area.get(area) or [])
        if texts:
            description = texts[index % len(texts)]
        elif person.coop_skill_ids:
            description = '%s. Работаю по направлению «%s».' % (
                ', '.join(person.coop_skill_ids.mapped('name')),
                specialization.name)
        else:
            description = 'Работаю по направлению «%s».' % specialization.name

        values = {
            'import_key': 'generated#%s' % person.id,
            'name': title,
            'description': '<p>%s</p>' % description if description else False,
            'partner_id': person.id,
            'coop_specialization_id': specialization.id,
            'skill_ids': [(6, 0, person.coop_skill_ids.ids)],
            'city': person.city or '',
            'ready_to_travel': index % 7 == 0,
            'experience_months': years * 12 + months,
            'rate': rate,
            'rate_kind': 'from' if index % 5 else 'piece',
            'rate_period': 'month',
            'state': 'published',
        }

        photo_name = (photo_by_spec.get(specialization.name)
                      or photo_by_area.get(area))
        photo = os.path.join(PHOTO_DIR, photo_name) if photo_name else ''
        if photo and os.path.exists(photo):
            with open(photo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read()).decode()
        else:
            # Снимка нет ни у специализации, ни у сферы — ставим знак по
            # роду занятий. Пустое место в строке каталога читается как
            # незагрузившаяся картинка, а знак — как оформление.
            values['image_1920'] = emblems.emblem(
                specialization.name, specialization.name)

        Offer.create(values)
        created += 1

    return created


# Специализации, у которых не нашлось ни одного предложения: среди
# участников нет человека, назвавшегося водителем или кладовщиком, и
# фильтр каталога предлагал пункты, по которым находилось пусто (12.10.2026).
# Предложение заводит участник из соседней сферы — тот, кому это дело
# правдоподобно по силам как второе: водитель из логистов и механиков,
# прораб из строителей. Человек может предлагать несколько навыков.
FILL = {
    'Водитель': {
        'from': ('Транспорт, логистика, перевозки', 'Автомобильный бизнес',
                 'Сельское хозяйство'),
        'rate': 75000,
        'skills': ('Категория B', 'Категория C', 'Грузоперевозки'),
        'texts': (
            'Права категорий B и C, стаж без аварий. Развожу грузы по городу '
            'и области, помогаю с погрузкой.',
            'Доставка продукции кооператива по магазинам и рынкам, '
            'путевые листы и накладные веду сам.',
        ),
    },
    'Диспетчер': {
        'from': ('Транспорт, логистика, перевозки', 'Административный персонал'),
        'rate': 60000,
        'skills': ('Диспетчеризация', 'Маршрутизация', '1С'),
        'texts': (
            'Принимаю заявки, строю маршруты, держу связь с водителями и '
            'складом. Работаю в 1С и картах.',
            'Диспетчерская смена: заявки, расписание машин, звонки клиентам '
            'о времени доставки.',
        ),
    },
    'Прораб, мастер СМР': {
        'from': ('Строительство, недвижимость', 'Бетонщик, арматурщик, каменщик',
                 'Столяр, плотник', 'Сварщик'),
        'rate': 110000,
        'skills': ('Организация работ', 'Чтение чертежей', 'Сметы'),
        'texts': (
            'Веду объект от нулевого цикла до сдачи: бригады, поставки, '
            'исполнительная документация.',
            'Частные дома и хозпостройки под ключ. Составлю смету, '
            'проконтролирую сроки и качество.',
        ),
    },
    'Администратор гостиницы': {
        'from': ('Туризм, гостиницы, рестораны', 'Административный персонал'),
        'rate': 55000,
        'skills': ('Бронирование', 'Работа с гостями', 'Кассовые операции'),
        'texts': (
            'Заселение и выселение, бронирования с площадок, касса, '
            'порядок в номерном фонде.',
            'Гостевой дом и турбаза: встречу гостей, отвечу на звонки, '
            'проведу оплату и отчёт за смену.',
        ),
    },
    'Кредитный специалист': {
        'from': ('Финансы, бухгалтерия', 'Продажи, обслуживание клиентов'),
        'rate': 80000,
        'skills': ('Кредитный анализ', 'Займы пайщикам', 'Документооборот'),
        'texts': (
            'Оформление займов в кредитном кооперативе: проверка заёмщика, '
            'договор, график платежей.',
            'Разбор финансового положения пайщика, подбор суммы и срока '
            'займа, сопровождение до погашения.',
        ),
    },
    'Кладовщик, Приемщик товаров': {
        'from': ('Транспорт, логистика, перевозки', 'Розничная торговля',
                 'Закупки'),
        'rate': 55000,
        'skills': ('Приёмка товара', 'Инвентаризация', 'Складской учёт'),
        'texts': (
            'Приёмка по накладным, размещение, отбор заказов, '
            'инвентаризация. Работал с ТСД и 1С.',
            'Склад кооператива: приму поставку, сверю с документами, '
            'выдам по заявкам и сведу остатки.',
        ),
    },
    'Разнорабочий': {
        'from': ('Бетонщик, арматурщик, каменщик', 'Столяр, плотник',
                 'Сельское хозяйство', 'Другое'),
        'rate': 45000,
        'skills': ('Погрузка-разгрузка', 'Подсобные работы', 'Уборка территории'),
        'texts': (
            'Погрузка и разгрузка, подготовка площадки, подсобные работы '
            'на стройке и в хозяйстве.',
            'Помогу на сезонных работах: уборка урожая, вывоз мусора, '
            'расчистка участка.',
        ),
    },
    # У этих предложение было одно, и то черновик: посетитель каталога
    # видел пустой пункт, а сфера консалтинга пустовала целиком.
    'Архитектор': {
        'from': ('Строительство, недвижимость', 'Искусство, развлечения, массмедиа'),
        'rate': 120000,
        'skills': ('Архитектурное проектирование', 'AutoCAD', 'Эскизный проект'),
        'texts': (
            'Проекты частных домов и общественных зданий: эскиз, рабочая '
            'документация, авторский надзор.',
            'Планировка участка и привязка дома к рельефу, согласования '
            'с администрацией.',
        ),
    },
    'Инженер строительного контроля': {
        'from': ('Строительство, недвижимость', 'Производство, сервисное обслуживание'),
        'rate': 100000,
        'skills': ('Технадзор', 'Приёмка работ', 'СНиП и СП'),
        'texts': (
            'Технадзор на стройке со стороны заказчика: скрытые работы, '
            'акты, предписания подрядчику.',
            'Приёмка квартиры или дома: проверю конструкции, инженерные '
            'сети и отделку, составлю перечень дефектов.',
        ),
    },
    'Агент по недвижимости': {
        'from': ('Строительство, недвижимость', 'Продажи, обслуживание клиентов',
                 'Административный персонал', 'Розничная торговля'),
        'rate': 70000,
        'skills': ('Подбор объектов', 'Сопровождение сделок', 'Проверка документов'),
        'texts': (
            'Подберу жильё или участок, проверю документы и сопровожу '
            'сделку до регистрации.',
            'Аренда и продажа помещений для кооперативов: показы, '
            'переговоры, договор.',
        ),
    },
    'Бизнес-консультант': {
        'from': ('Высший и средний менеджмент', 'Финансы, бухгалтерия',
                 'Стратегия, инвестиции, консалтинг'),
        'rate': 130000,
        'skills': ('Бизнес-планирование', 'Финансовая модель', 'Управленческий учёт'),
        'texts': (
            'Бизнес-план и финансовая модель для кооператива или '
            'фермерского хозяйства, подготовка к гранту.',
            'Разбор процессов небольшого производства: где теряются '
            'деньги и время, что поменять первым.',
        ),
    },
}
FILL_PER_SPECIALIZATION = 4


def _fill_empty_specializations(env, Offer, Partner, Skill, skill_type):
    Specialization = env['coop.specialization'].sudo()
    taken = set()
    created = 0
    for spec_name, plan in FILL.items():
        specialization = Specialization.search([('name', '=', spec_name)], limit=1)
        if not specialization:
            continue
        people = Partner.search([
            ('coop_is_participant', '=', True), ('is_company', '=', False),
            ('coop_specialization_id.category_id.name', 'in', plan['from']),
        ], order='id').filtered(
            # Без подтверждённого контакта навык снимается с публикации
            # (`load_verification`), и пункт фильтра остаётся пустым.
            lambda p: p.id not in taken and p.coop_level_at_least('contact'))
        if not people:
            continue

        skill_ids = []
        for name in plan['skills']:
            skill = Skill.search([('name', '=', name)], limit=1) or Skill.create(
                {'name': name, 'skill_type_id': skill_type.id})
            skill_ids.append(skill.id)

        title = spec_name.split(',')[0].strip()
        step = max(1, len(people) // FILL_PER_SPECIALIZATION)
        chosen = people[::step][:FILL_PER_SPECIALIZATION]
        # Авторов меньше, чем мест, — лишние записи прошлых прогонов
        # убираем: их владелец уже не проходит отбор.
        Offer.search([('import_key', 'in', [
            'skills.fill#%s#%s' % (spec_name, n)
            for n in range(len(chosen), FILL_PER_SPECIALIZATION)])]).unlink()
        for number, person in enumerate(chosen):
            taken.add(person.id)
            # Опознаём по специализации и номеру: id специализаций на
            # боевой и на копии разные, а название одно.
            key = 'skills.fill#%s#%s' % (spec_name, number)
            # Второе дело — опыт скромнее основного, но не больше лет
            # с восемнадцати.
            possible = max(0, (person.coop_age or 30) - 18)
            years = min(possible, number + person.id % 4)
            values = {
                'import_key': key,
                'name': title,
                'description': '<p>%s</p>' % plan['texts'][number % len(plan['texts'])],
                'partner_id': person.id,
                'coop_specialization_id': specialization.id,
                'skill_ids': [(6, 0, skill_ids)],
                'city': person.city or '',
                'ready_to_travel': number % 2 == 1,
                'experience_months': years * 12 + (person.id * 5) % 12,
                'rate': int(plan['rate'] * (0.85 + number * 0.1) / 1000) * 1000,
                'rate_kind': 'piece' if number == 3 else 'from',
                'rate_period': 'month',
                'state': _state_for(person.id),
            }
            photo = professions.photo_for('%s %s' % (title, number), spec_name)
            values['image_1920'] = photo or emblems.emblem(spec_name, spec_name)
            existing = Offer.search([('import_key', '=', key)], limit=1)
            if existing:
                existing.write(values)
            else:
                Offer.create(values)
                created += 1
    return created

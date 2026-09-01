# -*- coding: utf-8 -*-
"""Наполнение каталога людей из макета.

Сто человек, их профессии, навыки и фотографии лежат в `people.json` —
он собран разбором `people.html` прототипа, поэтому стенд и макет
показывают одних и тех же людей, и расхождение видно сразу.

Почему кодом, а не XML. Сто записей в XML — это полторы тысячи строк, в
которых при первой же правке макета никто не разберётся; фотографию в XML
пришлось бы держать base64-строкой, и файл распух бы до мегабайтов. Здесь
же исходные данные остаются человекочитаемым JSON.

Повторяемость держится на именах, а не на внешних идентификаторах.
Идентификаторы, заведённые в обход XML-загрузчика, Odoo при следующем
обновлении считает остатками предыдущей версии модуля и пытается удалить
— на людях это упирается во внешний ключ и роняет обновление целиком.
Имена же здесь уникальны по построению: и у профессии, и у категории есть
ограничение уникальности в базе, а человек в каталоге ровно один.
"""
import base64
import json
import logging
import os
from datetime import date

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
AVATAR_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img')

def _upsert(env, model, key, values):
    """Найти запись по ключевым полям или создать её.

    Идемпотентность здесь не украшение: загрузчик выполняется при каждой
    установке и обновлении модуля, и без сверки стенд после второго
    обновления содержал бы двести человек вместо ста.
    """
    domain = [(field, '=', value) for field, value in key.items()]
    record = env[model].search(domain, limit=1)
    if record:
        record.write(values)
        return record
    return env[model].create(dict(key, **values))


def _birthdate(age, seed):
    """Дата рождения из возраста.

    В макете указан возраст, а не дата — но хранить в базе возраст нельзя:
    через год все сто человек стали бы на год моложе, чем есть. Поэтому
    хранится дата, а возраст считается от неё. День и месяц разводятся по
    порядковому номеру, иначе у всех окажется один день рождения.
    """
    today = date.today()
    month = (seed % 12) + 1
    day = (seed * 7 % 27) + 1
    year = today.year - age
    if (month, day) > (today.month, today.day):
        year -= 1
        # Возраст считается от прошедшего дня рождения: у человека,
        # родившегося позже сегодняшней даты, в этом году он ещё не
        # наступил, значит родился он годом раньше.
    return date(year, month, day)


def load_people(env):
    path = os.path.join(HERE, 'people.json')
    with open(path, encoding='utf-8') as fh:
        people = json.load(fh)

    skill_type = env.ref('coop_demo.skill_type_craft')

    # Справочники создаются по факту встречаемости: список профессий и
    # навыков задан макетом, дублировать его отдельным файлом значит
    # завести второй источник правды, который разойдётся с первым.
    categories, professions, skills = {}, {}, {}

    for person in people:
        name = person['category']
        if name and name not in categories:
            categories[name] = _upsert(
                env, 'coop.profession.category', {'name': name}, {})

        name = person['profession']
        if name and name not in professions:
            professions[name] = _upsert(
                env, 'coop.profession', {'name': name},
                {'category_id': categories[person['category']].id})

        for name in person['skills']:
            if name not in skills:
                skills[name] = _upsert(
                    env, 'hr.skill',
                    {'name': name, 'skill_type_id': skill_type.id}, {})

    country_ru = env['res.country'].search([('code', '=', 'RU')], limit=1)

    for index, person in enumerate(people):
        values = {
            'name': person['name'],
            'is_company': False,
            'city': person['city'],
            'country_id': country_ru.id if country_ru else False,
            'coop_is_participant': True,
            'coop_verified': person['verified'],
            'coop_trust': person['trust'],
            'coop_birthdate': _birthdate(person['age'], index + 1),
            'coop_profession_id': professions[person['profession']].id,
            'coop_skill_ids': [(6, 0, [skills[s].id for s in person['skills']])],
        }

        # Число сделок выводится из доверия, а не задаётся отдельно: в
        # макете его нет, а брать случайное значение нельзя — доверие 99%
        # при двух сделках выглядит как ошибка, и это правильно, потому
        # что так оно и есть.
        values['coop_deals_done'] = max(1, (person['trust'] - 50) // 2)
        values['coop_deals_rated'] = max(1, values['coop_deals_done'] - (index % 3))

        avatar = os.path.join(AVATAR_DIR, person['avatar'].replace('/', os.sep))
        if os.path.exists(avatar):
            with open(avatar, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())

        # Часть людей из макета уже заведена вручную в reference-данных, и
        # на них ссылаются членство, сделка и учётная запись пайщика.
        # Поиск по имени эти записи подхватывает, а не плодит рядом
        # второго «Дашкевича Данила Игоревича».
        _upsert(env, 'res.partner',
                {'name': person['name'], 'is_company': False}, values)

    # Люди, заведённые в reference-данных до появления каталога: их
    # профессии в макете нет, а без неё они собираются в группу «не
    # задано» и выглядят как недозаполненные записи. Специализации взяты
    # из того же списка, что и у остальных: заводить ради троих отдельные
    # названия значит развести справочник на пустом месте.
    for name, profession in (
        ('Водянов Алексей Петрович', 'Сварщик'),
        ('Гончаров Пётр Ильич', 'Сварщик'),
        ('Ковалёв Игорь Степанович', 'Повар, кондитер'),
    ):
        partner = env['res.partner'].search([
            ('name', '=', name), ('is_company', '=', False)], limit=1)
        if partner and not partner.coop_profession_id and profession in professions:
            partner.coop_profession_id = professions[profession].id

    _logger.info(
        'Каталог людей: %s человек, %s профессий в %s категориях, %s навыков',
        len(people), len(professions), len(categories), len(skills))

# -*- coding: utf-8 -*-
"""Наполнение каталога организаций из макета.

Сто организаций из `organizations.html`: название, город, правовая форма,
специализация, уровень доверия и логотип.

Логотипы настоящих компаний из макета не переносятся: вместо них
рисуются собственные знаки (см. `emblems.py`). Организации, у которых в
макете была картинка, получают геометрическую эмблему, остальные —
букву названия; так сохраняется разнообразие каталога без чужих товарных
знаков.

Правовая форма выведена из названия, а не из атрибута `data-legal-group`
макета. В макете группа у заполняющих записей проставлена случайно и прямо
противоречит названию — есть «АО «Кедр»» в кооперативных и «ООО «Поморье»»
в некоммерческих. Название же несёт форму однозначно: организация так себя
и называет. Переносить в базу заведомо неверную классификацию нельзя —
по ней тут же начнут строиться группировки и правила.
"""
import base64
import json
import logging
import os

from . import emblems
from datetime import date

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img')


def _registered_on(seed):
    """Дата регистрации с разбросом.

    В макете её нет, но пустая дата у всех ста организаций читается как
    незаполненный справочник. Разброс по годам не декоративный: по нему
    видно, что каталог собран из организаций разного возраста, а не
    заведён одним днём.
    """
    year = 1995 + (seed * 7) % 30
    month = (seed % 12) + 1
    day = (seed * 5 % 27) + 1
    return date(year, month, day)


def load_organizations(env, specializations, marks):
    with open(os.path.join(HERE, 'organizations.json'), encoding='utf-8') as fh:
        orgs = json.load(fh)

    forms = {
        form.code: form
        for form in env['coop.legal.form'].search([])
    }
    country_ru = env['res.country'].search([('code', '=', 'RU')], limit=1)
    Partner = env['res.partner']

    created = 0
    for index, org in enumerate(orgs):
        form = forms.get(org['legal_form_code'])
        values = {
            'is_company': True,
            'city': org['city'],
            'country_id': country_ru.id if country_ru else False,
            'coop_is_participant': True,
            'coop_trust': org['trust'],
            'coop_legal_form_id': form.id if form else False,
            'coop_registered_on': _registered_on(index),
        }

        # ИНН, КПП и ОГРН намеренно не заполняются. Логотипы в макете взяты
        # у настоящих компаний, и подставить рядом номер с верной
        # контрольной суммой значит получить запись, неотличимую от
        # реальной выписки: такие данные потом расходятся по скриншотам и
        # презентациям. Пустое поле честнее выдуманного.
        specialization = specializations.get(org['specialization'])
        if specialization:
            values['coop_specialization_id'] = specialization.id

        # Настоящая эмблема из свободного набора, пока он не кончится.
        # Набор конечный, поэтому остальным достаётся знак-буква с
        # символом рода занятий — каталог от этого не разъезжается: в
        # макете было ровно так же, часть плиток с картинкой, часть с
        # буквой.
        mark = marks.next()
        if mark:
            with open(mark, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())
            values['coop_symbol_mark'] = True
        else:
            values['image_1920'] = emblems.monogram(org['name'], org['specialization'])
            values['coop_symbol_mark'] = False

        # Ключ — название вместе с городом, а не одно название. В макете
        # девять названий повторяются, и восемь из девяти пар стоят в
        # разных городах: «Кооператив «Борозда»» в Москве и во
        # Владивостоке — это две разные организации, а не одна дважды.
        # Схлопывать их по имени значит потерять записи на ровном месте.
        #
        # Заодно этот же поиск подхватывает организации из
        # reference-данных («Шукты», «Борозда», «Взаимопомощь», рабочая
        # группа платформы), на которые ссылается членство.
        existing = Partner.search([
            ('name', '=', org['name']), ('city', '=', org['city']),
            ('is_company', '=', True)], limit=1)
        if existing:
            # Правовую форму у заведённых вручную не трогаем: там она
            # проставлена осознанно, а в макете — выведена по названию.
            if existing.coop_legal_form_id:
                values.pop('coop_legal_form_id', None)
            existing.write(values)
        else:
            Partner.create(dict(values, name=org['name']))
            created += 1

    # Демонстрационные кооперативы из reference-данных. Именно на них
    # заведено членство, поэтому в каталоге они быть обязаны — иначе
    # состав участников есть, а организации в каталоге нет.
    #
    # Городу «Борозды» возвращается Тюмень: ранняя версия загрузчика
    # искала организацию по одному названию и переписала город на
    # Владивосток из одноимённой записи макета. Одноимённая запись
    # появится рядом отдельной организацией — это разные кооперативы в
    # разных городах, и в макете они тоже разные.
    for xmlid, city in (('coop_demo.org_shukty', 'Дербент'),
                        ('coop_demo.org_borozda', 'Тюмень'),
                        ('coop_demo.org_vzaimo', 'Пермь')):
        partner = env.ref(xmlid, raise_if_not_found=False)
        if not partner:
            continue
        values = {'coop_is_participant': True, 'city': city}
        if not partner.coop_legal_form_id:
            values['coop_legal_form_id'] = forms['po'].id
        if not partner.image_1920:
            values['image_1920'] = emblems.monogram(
                partner.name, partner.coop_specialization_id.name)
            values['coop_symbol_mark'] = False
        partner.write(values)

    _logger.info('Каталог организаций: %s записей, создано %s, настоящих '
                 'эмблем роздано %s из %s', len(orgs), created,
                 marks.used, marks.total)

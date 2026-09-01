# -*- coding: utf-8 -*-
"""Наполнение каталога организаций из макета.

Сто организаций из `organizations.html`: название, город, правовая форма,
специализация, уровень доверия и логотип.

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
import re
from datetime import date

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR = os.path.join(os.path.dirname(HERE), 'static', 'img')

# Цвета монограммы: у трёх четвертей организаций в макете нет картинки, и
# вместо неё стоит буква на подложке фирменного оттенка. Повторяем это, а
# не подставляем серую заглушку «нет изображения»: в каталоге из ста плиток
# сотня одинаковых заглушек хуже, чем сотня разных букв.
MONOGRAM_BG = '#e3efed'
MONOGRAM_FG = '#0e4f4a'


def _monogram(name):
    """Логотип-монограмма: первая буква названия на светлой подложке.

    Буква берётся из собственного имени организации, а не из формы: у
    «ООО «Мириталь»» это «М», иначе половина каталога оказалась бы под
    буквой «О», а вторая половина под «П».

    Кегль подобран по макету: там буква занимает около седьмой части
    ширины плитки. Крупнее — и плитка читается как обложка, а не как
    карточка организации.
    """
    quoted = re.search(r'[«"]\s*(\S)', name)
    letter = (quoted.group(1) if quoted else name.strip()[:1]).upper()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256">'
        '<rect width="256" height="256" fill="%s"/>'
        '<text x="50%%" y="50%%" fill="%s" font-family="Manrope, sans-serif" '
        'font-size="38" font-weight="700" text-anchor="middle" '
        'dominant-baseline="central">%s</text></svg>'
    ) % (MONOGRAM_BG, MONOGRAM_FG, letter)
    return base64.b64encode(svg.encode('utf-8'))


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


def load_organizations(env, specializations):
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

        # В макете путь пишется от корня прототипа («img/org-logos/…»), а
        # в модуле логотипы лежат в static/img/org-logos. Ведущий «img/»
        # снимаем, иначе получится «static/img/img/…» и все сто плиток
        # молча уедут на монограммы.
        relative = re.sub(r'^(images?|img)/', '', org['logo']) if org['logo'] else ''
        logo = os.path.join(LOGO_DIR, relative.replace('/', os.sep)) if relative else ''
        if logo and os.path.exists(logo):
            with open(logo, 'rb') as fh:
                values['image_1920'] = base64.b64encode(fh.read())
            values['coop_has_own_logo'] = True
        else:
            values['image_1920'] = _monogram(org['name'])
            values['coop_has_own_logo'] = False

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
            values['image_1920'] = _monogram(partner.name)
            values['coop_has_own_logo'] = False
        partner.write(values)

    _logger.info('Каталог организаций: %s записей, из них создано %s',
                 len(orgs), created)

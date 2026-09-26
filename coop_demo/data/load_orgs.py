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
import random
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


# Переименования организаций наполнения. Загрузчик ищет организацию по
# названию и городу, поэтому правка названия в выгрузке заводит вторую
# запись вместо переименования первой — с теми же членами, проектами и
# вакансиями. Так и вышло с «ДАО КООПЕХ»: старая опечатка в названии
# платформы держалась в наполнении, а её исправление раздвоило
# организацию.
RENAMED = {
    'ДАО КООПТЕХ': 'ДАО КООПЕХ',
}


def _renamed(Partner, org):
    """Найти организацию по прежнему названию и переименовать."""
    was = RENAMED.get(org['name'])
    if not was:
        return Partner.browse()
    # По названию, без города. Город у организации мог быть проставлен
    # позже — обогащением профиля, — и в выгрузке его нет. Совпадения по
    # названию достаточно: список переименований ведётся руками и
    # содержит имена самой платформы, а не рядовых кооперативов, среди
    # которых тёзки в разных городах — обычное дело.
    old = Partner.search([
        ('name', '=', was), ('is_company', '=', True)], limit=1)
    if old:
        old.name = org['name']
    return old


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
            # Доверие не выдумывается: его считает модуль сделок по
            # настоящим отзывам. Вписанное здесь число означало бы
            # оценку, за которой ничего нет.
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
        #
        # Без города в макете — ДАО, узлы сети — ищем по одному названию:
        # город им ставит позже другой загрузчик, и поиск «название +
        # пустой город» при следующем прогоне их уже не находил. Каждое
        # обновление заводило ещё по три «ДАО КООПТЕХ», «ДАО «ОткрытыйГород»»,
        # «ДАО «Цифровой кооператив»» — к 26.09.2026 их стало по 110
        # (решение 416, находка про дубли). Город таким не переписываем.
        if org['city']:
            existing = Partner.search([
                ('name', '=', org['name']), ('city', '=', org['city']),
                ('is_company', '=', True)], limit=1)
        else:
            existing = Partner.search([
                ('name', '=', org['name']), ('is_company', '=', True)],
                order='id', limit=1)
            values.pop('city', None)
        if not existing:
            existing = _renamed(Partner, org)
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

def link_organizations(env):
    """Связать организации между собой: союзы, учредители, поставщики.

    На карточке организации есть полка «Связанные организации» — с кем
    она работает. Без данных она пуста у всех ста восьмидесяти девяти, и
    не видно ни того, как полка выглядит, ни того, что связь бывает
    разной: союз это одно, поставщик другое.

    Показываются только подтверждённые второй стороной, поэтому здесь
    они сразу подтверждённые: связь, объявленная в одностороннем
    порядке, на карточке не появится, и полка осталась бы пустой.

    Безвредно при повторе: связи заводятся только тем, у кого их ещё нет.
    """
    Link = env['coop.org.link'].sudo()
    Partner = env['res.partner'].sudo()
    organizations = Partner.search([
        ('is_company', '=', True), ('coop_is_participant', '=', True)],
        order='id')
    if len(organizations) < 4:
        return 0

    # Союзы и объединения — те, у кого в названии это сказано прямо.
    unions = organizations.filtered(
        lambda o: any(word in (o.name or '').lower()
                      for word in ('союз', 'ассоциац', 'объединен', 'федерац')))
    rest = organizations - unions

    rnd = random.Random(20260915)
    created = 0
    for number, organization in enumerate(rest):
        if_any = Link.search_count(['|',
            ('org_id', '=', organization.id),
            ('other_id', '=', organization.id)])
        if if_any:
            continue

        links = []
        # В союз входит примерно каждая третья: не все кооперативы
        # состоят в объединениях, и показывать обратное было бы неправдой.
        if unions and number % 3 == 0:
            links.append((unions[number % len(unions)], 'union'))
        # Поставщик и покупатель — из своего же города, если есть: связи
        # чаще складываются по соседству.
        neighbours = rest.filtered(
            lambda o: o.city == organization.city and o != organization)
        set_of = neighbours or (rest - organization)
        if set_of:
            links.append((set_of[number % len(set_of)], 'supplier'))
        if len(set_of) > 1 and number % 2 == 0:
            links.append((set_of[(number + 1) % len(set_of)], 'partner'))

        for other_org, kind in links:
            if other_org == organization:
                continue
            with env.cr.savepoint():
                Link.create({
                    'org_id': organization.id,
                    'other_id': other_org.id,
                    'kind': kind,
                    'confirmed': True,
                })
            created += 1

    _logger.info('Связи организаций: заведено %s', created)
    return created

def give_services(env):
    """Отдать часть предложений навыков организациям.

    Полка «Услуги» на карточке организации появляется, когда услуга у
    неё есть, — владелец 15 сентября 2026: «услуги (появляется при
    добавлении услуги)». Проверено: услуг не было ни у одной из ста
    восьмидесяти девяти, и полка не показалась бы никогда.

    Услуга на платформе — это предложение навыка: тот же каталог и та же
    карточка. Организация предлагает услуги наравне с человеком, и
    заводить ей отдельную сущность незачем.

    Передаём существующие предложения, а не заводим новые: у них есть
    снимок, описание и цена, а свежесозданные «Услуга 1, Услуга 2»
    выглядели бы заглушками.

    Безвредно при повторе: организации, у которых услуги уже есть,
    пропускаются.
    """
    Offer = env['coop.skill.offer'].sudo()
    Partner = env['res.partner'].sudo()
    organizations = Partner.search([
        ('is_company', '=', True), ('coop_is_participant', '=', True)],
        order='id')
    if not organizations:
        return 0

    # Только у людей и только опубликованные: у организации уже может
    # быть своё, а снятое с публикации на витрине не показывается.
    free = Offer.search([
        ('state', '=', 'published'),
        ('partner_id.is_company', '=', False),
    ], order='id')
    if not free:
        _logger.info('Услуги организаций: свободных предложений нет')
        return 0

    # Примерно каждой третьей организации — одна-две услуги. Не всем:
    # услуги оказывает не всякий кооператив, и полка у всех подряд
    # выглядела бы одинаково выдуманной.
    given = 0
    stream = iter(free)
    for number, organization in enumerate(organizations):
        if number % 3:
            continue
        if Offer.search_count([('partner_id', '=', organization.id)]):
            continue
        how_many = 1 + (number % 2)
        for _ in range(how_many):
            offer = next(stream, None)
            if offer is None:
                _logger.info('Услуги организаций: отдано %s, предложения кончились',
                             given)
                return given
            with env.cr.savepoint():
                offer.write({'partner_id': organization.id})
            given += 1

    _logger.info('Услуги организаций: отдано %s предложений', given)
    return given


# Уникальные частичные индексы, которых мастер слияния движка не видит
# (он распознаёт только ограничения): таблица, ключ, колонки-контакты.
_PARTIAL_UNIQUE = [
    ('coop_membership', ['partner_id', 'organization_id'], ['partner_id', 'organization_id']),
    ('coop_community_member', ['community_id', 'partner_id'], ['partner_id']),
    ('discuss_channel_member', ['channel_id', 'partner_id'], ['partner_id']),
    ('mail_message_reaction', ['message_id', 'content', 'partner_id'], ['partner_id']),
    ('mail_notification', ['mail_message_id', 'res_partner_id'], ['res_partner_id']),
]


def _clear_merge_conflicts(env, dst, src):
    """Убрать строки копий, которые после переноса на исходную запись
    совпали бы по уникальному ключу с её строками или друг с другом, и
    строки, где организация оказалась бы в составе самой себя."""
    cr = env.cr
    for table, key, partner_cols in _PARTIAL_UNIQUE:
        cr.execute("SELECT to_regclass(%s)", [table])
        if not cr.fetchone()[0]:
            continue

        def mapped(alias, col):
            if col in partner_cols:
                return (f'(CASE WHEN {alias}.{col} = ANY(%(src)s) THEN %(dst)s '
                        f'ELSE {alias}.{col} END)')
            return f'{alias}.{col}'

        same = ' AND '.join('%s IS NOT DISTINCT FROM %s' % (mapped('d', c), mapped('s', c))
                            for c in key)
        touches = ' OR '.join(f's.{c} = ANY(%(src)s)' for c in partner_cols)
        cr.execute("""
            DELETE FROM %(t)s s
             WHERE (%(touches)s)
               AND EXISTS (SELECT 1 FROM %(t)s d
                            WHERE d.id <> s.id AND %(same)s
                              AND (d.id < s.id OR NOT (%(dtouch)s)))
        """ % {'t': table, 'touches': touches, 'same': same,
               'dtouch': touches.replace('s.', 'd.')}, {'src': list(src), 'dst': dst})
        if len(partner_cols) > 1:
            a, b = partner_cols[:2]
            cr.execute("DELETE FROM %s s WHERE %s = %s" % (table, mapped('s', a), mapped('s', b)),
                       {'src': list(src), 'dst': dst})


def merge_duplicate_orgs(env):
    """Слить размножившиеся организации без города в исходную запись.

    До починки поиска каждое обновление заводило по новой копии ДАО без
    города (см. `load_organizations`). Копии сливаются штатным слиянием
    контактов движка: все ссылки на копии — проекты, вакансии, сделки,
    состав, связи — переходят на исходную (самую раннюю) запись, копии
    удаляются. Движок сливает не больше трёх за раз — идём тройками.
    Повторный запуск ничего не делает: копий уже нет.
    """
    with open(os.path.join(HERE, 'organizations.json'), encoding='utf-8') as fh:
        orgs = json.load(fh)
    names = sorted({org['name'] for org in orgs if not org['city']})
    Partner = env['res.partner'].sudo().with_context(active_test=False)
    Wizard = env['base.partner.merge.automatic.wizard'].sudo()
    merged = 0
    for name in names:
        found = Partner.search([('name', '=', name), ('is_company', '=', True),
                                ('user_ids', '=', False)], order='id')
        if len(found) < 2:
            continue
        keep, copies = found[0], found[1:]
        _clear_merge_conflicts(env, keep.id, copies.ids)
        for start in range(0, len(copies), 2):
            chunk = copies[start:start + 2]
            Wizard._merge((keep | chunk).ids, keep, extra_checks=False)
            merged += len(chunk)
        _logger.info('Организации: «%s» — слито копий %s в №%s', name, len(copies), keep.id)
    return merged

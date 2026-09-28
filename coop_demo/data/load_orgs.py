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


# Всем организациям — разные названия (владелец 28.09.2026: «сделай всем
# разные имена»). Тёзки в разных городах в макете были нарочно, но на
# платформе они читались как одна организация, записанная дважды:
# «Кооператив «Борозда»» трижды в портфеле, два «Покоса» в поиске.
#
# Переименованная запись должна находиться и следующим прогоном — иначе
# загрузчик по паре «название + город» не узнает её и заведёт тёзку
# заново, а переименование заведёт ещё одну. Поэтому каждое
# переименование запоминается: «прежнее название|город» → новое.
RENAMES_PARAM = 'coop_demo.org_renames'

# Новые названия — слова того же ряда, что в макете: короткие, русские,
# про землю и ремесло. Правовая форма («Кооператив», «АО», «ТСЖ»)
# сохраняется: меняется имя, а не вид организации.
BRANDS = [
    'Нива', 'Сенокос', 'Кедр', 'Берег', 'Опора', 'Слобода',
    'Жатва', 'Лад', 'Колос', 'Вереск', 'Подворье', 'Пахарь', 'Устье',
    'Околица', 'Житница', 'Горница', 'Пойма', 'Бор', 'Раздолье',
    'Ключи', 'Родное', 'Сруб', 'Гумно', 'Зимовье', 'Перелесок',
]

# Названия без «кавычек» подбором не заменить — для них своё.
SPECIAL = {
    'ДАО КООПТЕХ — рабочая группа': 'ДАО КООПТЕХ — оператор платформы',
}


def _renames(env):
    raw = env['ir.config_parameter'].sudo().get_param(RENAMES_PARAM) or '{}'
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _renamed_by_city(Partner, renames, org):
    """Организация, переименованная ради уникальности названия."""
    new = renames.get('%s|%s' % (org['name'], org['city'] or ''))
    if not new:
        return Partner.browse()
    domain = [('name', '=', new), ('is_company', '=', True)]
    if org['city']:
        domain.append(('city', '=', org['city']))
    return Partner.search(domain, limit=1)


def unique_org_names(env):
    """Разные названия у всех действующих организаций. Идемпотентно."""
    Partner = env['res.partner'].sudo().with_context(tracking_disable=True)
    cr = env.cr
    cr.execute("""
        SELECT name FROM res_partner
         WHERE is_company AND active
         GROUP BY name HAVING count(*) > 1
    """)
    names = [row[0] for row in cr.fetchall()]
    if not names:
        return 0
    main = env.ref('base.main_partner', raise_if_not_found=False)
    cr.execute("SELECT res_id FROM ir_model_data WHERE model = 'res.partner'")
    with_xmlid = {row[0] for row in cr.fetchall()}
    taken = set(Partner.search([('is_company', '=', True)]).mapped('name'))
    # Название в кавычках тоже не повторяется ни у кого: «АО «Нива»» рядом
    # с «ООО «Нива»» и «ТСЖ «Нива»» формально разные, но читаются как одна
    # сеть тёзок — то, от чего и избавляемся.
    used = {n.partition('«')[2].rstrip('»') for n in taken if '«' in n}
    renames = _renames(env)
    Membership = env['coop.membership'].sudo() if 'coop.membership' in env else None
    Deal = env['coop.deal'].sudo() if 'coop.deal' in env else None

    def weight(partner):
        # Название сохраняет та, на которой держится больше: главная
        # компания, запись справочника, затем — члены и сделки.
        # `is not None`, а не просто `if Membership`: пустой набор записей
        # ложен, и тогда не считалось бы ничего — название оставалось бы
        # у меньшего номера (так и вышло с «Покосом» на стенде 28.09).
        members = (Membership.search_count([('organization_id', '=', partner.id)])
                   if Membership is not None else 0)
        deals = (Deal.search_count(['|', ('party_a_id', '=', partner.id),
                                    ('party_b_id', '=', partner.id)])
                 if Deal is not None else 0)
        return (partner == main, partner.id in with_xmlid, members + deals, -partner.id)

    renamed = 0
    for name in names:
        group = Partner.search([('name', '=', name), ('is_company', '=', True)])
        keep = max(group, key=weight)
        for partner in (group - keep).sorted('id'):
            new = SPECIAL.get(name) if SPECIAL.get(name) not in taken else None
            if not new:
                head, sep, _tail = name.partition('«')
                prefix = head if sep else name + ' '
                brand = next((b for b in BRANDS if b not in used), None)
                new = '%s«%s»' % (prefix, brand) if brand else None
            if not new:
                _logger.warning('Не нашлось свободного названия для «%s» (%s)', name, partner.id)
                continue
            renames['%s|%s' % (name, partner.city or '')] = new
            partner.name = new
            taken.add(new)
            used.add(new.partition('«')[2].rstrip('»'))
            renamed += 1
    env['ir.config_parameter'].sudo().set_param(
        RENAMES_PARAM, json.dumps(renames, ensure_ascii=False, sort_keys=True))
    _logger.info('Названия организаций: переименовано %s', renamed)
    return renamed


def load_organizations(env, specializations, marks):
    with open(os.path.join(HERE, 'organizations.json'), encoding='utf-8') as fh:
        orgs = json.load(fh)
    renames = _renames(env)

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
            existing = _renamed_by_city(Partner, renames, org)
        if not existing:
            existing = _renamed(Partner, org)
        if existing:
            # Правовую форму у заведённых вручную не трогаем: там она
            # проставлена осознанно, а в макете — выведена по названию.
            if existing.coop_legal_form_id:
                values.pop('coop_legal_form_id', None)
            # Снимок — только при заведении. Раньше он переписывался при
            # каждом прогоне: каждое обновление заново клало всем
            # организациям знак из набора и откатывало замену пустых
            # снимков монограммой (решение 416).
            values.pop('image_1920', None)
            values.pop('coop_symbol_mark', None)
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


def repair_empty_logos(env):
    """Снимок организации, у которого плитка выходит пустой, — монограммой.

    Части организаций из свободного набора знаков достались чёрные буквы
    на прозрачном фоне (у «ДАО «ОткрытыйГород»», «ДАО «Цифровой
    кооператив»»): уменьшенная копия для плитки выходила пустой — сто с
    небольшим байт, — и в каталоге стоял чёрный квадрат. Им ставится
    монограмма с цветным фоном, как организациям без логотипа. Повторный
    запуск ничего не меняет: у монограммы копия полноценная.
    """
    with open(os.path.join(HERE, 'organizations.json'), encoding='utf-8') as fh:
        by_name = {org['name']: org for org in json.load(fh)}
    Attachment = env['ir.attachment'].sudo()
    thin = Attachment.search([('res_model', '=', 'res.partner'), ('res_field', '=', 'image_128'),
                              ('file_size', '<', 400)])
    Partner = env['res.partner'].sudo()
    fixed = 0
    for partner in Partner.browse(thin.mapped('res_id')).exists():
        if not partner.is_company:
            continue
        org = by_name.get(partner.name, {})
        partner.write({'image_1920': emblems.monogram(partner.name, org.get('specialization', '')),
                       'coop_symbol_mark': False})
        fixed += 1
    if fixed:
        _logger.info('Организации: пустые снимки заменены монограммой у %s', fixed)
    return fixed


def spread_cooperative_kinds(env):
    """Вид кооператива у демо-организаций формы «ПО» — с разбросом.

    Решение 425: форма «ПО» одна на потребительское общество по 3085-1 и
    на прочие потребительские кооперативы; по умолчанию ставится
    общество, и без разброса второй вид в каталоге не виден. Каждый
    третий — потребительский кооператив.
    """
    Partner = env['res.partner'].sudo().with_context(tracking_disable=True)
    orgs = Partner.search([('coop_legal_form_id.code', '=', 'po')], order='id')
    changed = 0
    for index, org in enumerate(orgs):
        kind = 'consumer' if index % 3 == 1 else 'consumer_society'
        if org.coop_cooperative_kind != kind:
            org.coop_cooperative_kind = kind
            changed += 1
    _logger.info('Вид кооператива у ПО: %s организаций, изменено %s', len(orgs), changed)


def drop_non_coop_shares(env):
    """Паевые счета у организаций, которые не кооперативы, — убрать.

    27.09.2026 СНТ перестало считаться кооперативом (ГК 123.12–123.14,
    217-ФЗ: товарищество собственников без паёв). Демо-загрузка успела
    завести у трёх СНТ полсотни паевых счетов — у товарищества их быть не
    может, и в «Портфеле» они показывали бы пай, которого нет. Новые не
    появятся: счета заводятся только из членства в кооперативе.
    """
    if 'coop.share.account' not in env:
        return
    accounts = env['coop.share.account'].sudo().search(
        [('cooperative_id.coop_is_cooperative', '=', False)])
    if accounts:
        _logger.info('Паевые счета вне кооперативов: удалено %s', len(accounts))
        accounts.unlink()

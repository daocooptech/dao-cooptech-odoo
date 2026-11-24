# -*- coding: utf-8 -*-
"""Карточки сбора рабочим проектам (№ 455, кусок 3).

Владелец 15.11.2026: «так это и есть задача сделать у всех проектов во
вкладке управление проектом полноценные страницы с откликами и
аналитикой». Страница проекта в «Управлении проектами» берёт заявки на
потребности и четыре вкладки аналитики с карточки сбора
(`coop.project.project_id`). У 178 проектов, заведённых без сбора
(`load_project_work`: кровля цеха, переход на ЭДО, баня, фестиваль…),
карточки не было — под «Описанием» белое поле.

Каждому такому проекту — карточка, как если бы организация или человек
собирали на него ресурсы через платформу:

- инициатор — заказчик проекта, менеджер — его руководитель (решение
  685); вид — по правовой форме организации, у людей — по делу;
- состояние — по этапу ведения: «Подготовка», «Закупки», «Работы»,
  «Приёмка» — запущен; «Итоги и распределение» — завершён;
  «Остановлен» — заморожен, каждый третий — отменён;
- потребности и отклики заводят общие загрузчики (`load_project_needs`,
  `load_intangible_needs`, ЦФА) — они пропускают наполненные проекты и
  подхватывают новые; темы рабочих проектов добавлены в `BY_TOPIC`;
- здесь — вклады до правдоподобной готовности (от суммы потребностей,
  решение 652), отклонённые, ждущие и возвращённые вклады, контракты,
  вклад нематериальным активом и лента фото по теме.

Проект без заказчика («MVP DAO COOPTECH» — проект самой платформы) не
трогаем: собирать на него от чужого имени нечего.

Идемпотентно: проект с карточкой пропускается, у карточки (ключ
`work-card#<id проекта>`) доводится только недостающее.
"""
import base64
import logging
import random
from datetime import timedelta

from odoo import fields

from . import load_intangible_needs, load_media_gallery, load_project_deals
from . import load_project_needs, load_projects
from .demo_only import DEMO

_logger = logging.getLogger(__name__)

KEY = 'work-card#%s'

# Тема → (вид у человека, рубрика, подрубрика, снимки, контракты, коротко).
# Вид у организации берётся из её правовой формы, у человека — отсюда.
THEMES = {
    'Ремонт кровли производственного цеха': (
        'commercial', 'Малый бизнес и ремёсла', None,
        ('metal-roof', 'scaffolding', 'mineral-wool', 'construction-foreman'),
        ('Подряд на кровельные работы', 'Поставка мембраны и утеплителя',
         'Аренда автовышки'),
        'Меняем кровлю цеха на мембранную с утеплением — без остановки линии.'),
    'Переход на электронный документооборот': (
        'commercial', 'Технологии и инновации', None,
        ('documents-stamp', 'accountant-office', 'laptop-desk', 'office-desk'),
        ('Подключение к оператору электронного документооборота',
         'Настройка маршрутов согласования'),
        'Договоры, акты и счета — на электронную подпись и обмен через оператора.'),
    'Открытие пункта выдачи заказов': (
        'commercial', 'Малый бизнес и ремёсла', None,
        ('shop-counter', 'warehouse-shelves', 'delivery-van', 'cashier'),
        ('Аренда помещения под пункт выдачи', 'Поставка стеллажей и сканеров',
         'Изготовление и монтаж вывески'),
        'Пункт выдачи совместных закупок у остановки: стеллажи, касса, вывеска.'),
    'Внедрение складского учёта': (
        'commercial', 'Технологии и инновации', None,
        ('warehouse-shelves', 'warehouse-worker', 'warehouse',
         'logistics-dispatcher'),
        ('Поставка терминалов сбора данных', 'Настройка учётной системы'),
        'Остатки в системе — как на полках: приёмка, ячейки, штрихкоды.'),
    'Энергоаудит и замена освещения': (
        'commercial', 'Экология и природа', 'Возобновляемая энергетика',
        ('electrician-work', 'power-meter', 'electrical-supplies', 'electrician'),
        ('Энергетическое обследование здания', 'Поставка светодиодных светильников',
         'Электромонтажные работы'),
        'Обследуем здание и меняем освещение на светодиодное с датчиками.'),
    'Подготовка к сезону заготовки': (
        'commercial', 'Сельское хозяйство и еда', 'Пищевое производство',
        ('berry-harvest', 'cold-storage', 'plastic-crates', 'pine-nuts'),
        ('Аренда рефрижератора на сезон', 'Поставка тары',
         'Закупка сырья на первую очередь'),
        'Цех, тара, приёмные пункты и сборщики — к сезону ягод и грибов.'),
    'Сертификация продукции': (
        'commercial', 'Сельское хозяйство и еда', 'Пищевое производство',
        ('lab-equipment', 'documents-stamp', 'glass-jars', 'factory-operator'),
        ('Лабораторные испытания продукции', 'Разработка технических условий'),
        'Испытания, технические условия и маркировка — чтобы взяли крупные сети.'),
    'Годовое общее собрание пайщиков': (
        'nonprofit', 'Общественные инициативы', None,
        ('assembly-hall', 'community-meeting', 'business-meeting'),
        ('Аренда зала на собрание', 'Печать бюллетеней и отчётов'),
        'Повестка, извещение пайщиков, отчёт правления, голосование и протокол.'),
    'Ремонт квартиры под сдачу': (
        'commercial', 'Архитектура и урбанистика', None,
        ('building-renovation', 'interior-designer', 'plumber', 'sofa'),
        ('Подряд на отделочные работы', 'Замена электропроводки'),
        'Косметический ремонт однокомнатной квартиры к сезону аренды.'),
    'Фестиваль соседских огородов': (
        'nonprofit', 'Культура и искусство', 'Культура и досуг',
        ('harvest-festival', 'seed-swap', 'community-gathering',
         'vegetable-field'),
        ('Аренда шатров и звука', 'Ведение фестиваля'),
        'Обмен рассадой и семенами, мастер-классы и ярмарка урожая для соседей.'),
    'Курс «Учёт для небольшого кооператива»': (
        'commercial', 'Образование и наука', 'Дополнительное образование',
        ('workshop-class', 'accountant', 'accountant-office', 'laptop-desk'),
        ('Видеосъёмка и монтаж занятий', 'Аренда аудитории'),
        'Восемь занятий о паевых взносах, отчётности и расчётах с пайщиками.'),
    'Строительство бани на участке': (
        'commercial', 'Архитектура и урбанистика', None,
        ('timber-beam', 'carpenter', 'masonry-stove', 'wood-planks'),
        ('Поставка сруба из бруса', 'Подряд на фундамент',
         'Монтаж печи и дымохода'),
        'Баня из бруса 6×4: фундамент, сруб, кровля и печь — вехами.'),
    'Перевод семейного бюджета в таблицу': (
        'nonprofit', 'Образование и наука', None,
        ('finance-money', 'laptop-desk', 'data-analytics', 'tablet'),
        ('Консультация по семейному бюджету',),
        'Учёт доходов и расходов семьи — из тетради в общую таблицу.'),
    'Сбор гуманитарной помощи в приют': (
        'nonprofit', 'Благотворительность', None,
        ('volunteer-coordinator', 'plastic-crates', 'kittens',
         'volunteer-cleanup'),
        ('Доставка собранного в приют',),
        'Корм, лекарства и тёплые вещи для приюта: пункты приёма и доставка.'),
    'Круглогодичная теплица': (
        'commercial', 'Сельское хозяйство и еда', 'Городское земледелие',
        ('greenhouse', 'greenhouse-interior', 'greenhouse-tomato',
         'greenhouse-lettuce'),
        ('Поставка поликарбоната и каркаса', 'Монтаж системы полива'),
        'Теплица с подогревом: зелень и томаты круглый год для пайщиков.'),
}

# Вид проекта по правовой форме организации (коды справочника форм).
COOP_FORMS = ('po', 'pk', 'spk', 'sppk', 'kpk', 'skpk', 'artel', 'zhsk')
NONPROFIT_FORMS = ('ano', 'fond', 'oo', 'association', 'tszh', 'union')

# Этап ведения → состояние сбора. Проект в управлении создаётся при
# запуске, поэтому «Идея» и «Сбор» у рабочих проектов не бывает.
STAGE_STATE = {
    'Итоги и распределение': 'done',
    'Остановлен': 'frozen',
}

# Сколько собрано против нужного, %: запущенный набрал порог, завершённый —
# всё, остановленный — как получилось.
READINESS = {
    'running': (72, 112),
    'done': (100, 124),
    'frozen': (48, 96),
    'cancelled': (26, 64),
}


def load_work_cards(env):
    Task = env['project.project'].sudo().with_context(active_test=True)
    Card = env['coop.project'].sudo().with_context(tracking_disable=True)
    linked = set(Card.with_context(active_test=False).search(
        [('project_id', '!=', False)]).mapped('project_id').ids)
    work = Task.search(DEMO + [('id', 'not in', list(linked)),
                        ('partner_id', '!=', False)], order='id')

    people = env['res.partner'].sudo().search([
        ('coop_is_participant', '=', True), ('is_company', '=', False)],
        order='id')
    if not people:
        _logger.info('Карточки рабочих проектов: нет участников, пропуск')
        return 0

    rnd = random.Random(20261116)
    made = Card.browse()
    stopped = {}
    for project in work:
        theme = _theme(project.name)
        if not theme:
            continue
        values = _card_values(env, project, theme, rnd)
        try:
            with env.cr.savepoint():
                card = Card.create(values)
                _economic_model(env, card, project.id)
                load_projects._investment_basis(card, values['import_key'])
        except Exception as error:
            _logger.warning('Карточка проекта «%s» не заведена: %s',
                            project.name, error)
            continue
        made |= card
        target = STAGE_STATE.get(project.stage_id.name)
        if target == 'frozen' and project.id % 3 == 0:
            target = 'cancelled'
        stopped[card.id] = target

    if made:
        # Потребности, отклики, нематериальное — общими загрузчиками: они
        # пропускают наполненные проекты и подхватывают новые карточки.
        # Предел у первого — от числа проектов, иначе последние по порядку
        # остаются без потребностей.
        load_project_needs.load_project_needs(env, target=10 * len(made))
        load_project_needs.link_offers_to_resources(env)
        load_project_needs.set_ownership_kinds(env)
        load_project_needs.fill_offer_notes(env)
        if 'coop.intangible' in env:
            load_intangible_needs.load_intangible_needs(env)
        env.flush_all()

    cards = Card.search([('import_key', '=like', 'work-card#%')], order='id')
    funded = dealt = shared = shot = 0
    for index, card in enumerate(cards):
        # Актив — до доливки: его оценка тоже в «собрано».
        shared += _intangible(env, card, index, rnd)
        # Доливка — только только что заведённым: у них вкладов без
        # потребности ещё нет, а признак «уже наполнен» у карточки с
        # откликами на вакансии не отличить от наполненной.
        if card in made:
            env.flush_all()
            funded += _fund(env, card, people, rnd, index, stopped.get(card.id))
        dealt += _deals(env, card, index, rnd)
        shot += _photos(env, card)
    env.flush_all()

    if made:
        load_project_deals.link_cfa_to_projects(env)
        load_project_deals.place_project_cfa(env)

    # Состояние — последним: заморозка и отмена снимают объявления и
    # рассчитываются с вкладчиками тем же кодом, что и кнопка, а
    # завершённому проекту искать больше нечего.
    finished = 0
    for card in made:
        target = stopped.get(card.id)
        if target == 'done':
            card._withdraw_listings()
            card.contribution_ids.filtered(
                lambda c: c.state == 'offered').write({'state': 'expired'})
            card.state = 'done'
        elif target == 'frozen':
            card.write({'resume_state': 'running', 'state': 'frozen'})
        elif target == 'cancelled':
            card.state = 'cancelled'
        else:
            continue
        finished += 1

    _logger.info('Карточки рабочих проектов: заведено %s, вкладов %s, '
                 'контрактов %s, вкладов активами %s, снимков %s, '
                 'остановлено и завершено %s', len(made), funded, dealt,
                 shared, shot, finished)
    return len(made)


def _theme(name):
    base = (name or '').split(' — ')[0].split(', ')[0].strip()
    return base if base in THEMES else None


def _card_values(env, project, theme, rnd):
    kind_for_person, category, subcategory, _subjects, _deals_, summary = \
        THEMES[theme]
    partner = project.partner_id
    lead = project.user_id.partner_id
    city = ''
    if ' — ' in (project.name or ''):
        city = project.name.split(' — ', 1)[1].strip()
    start = project.date_start or project.create_date.date()
    Category = env['coop.project.category'].sudo()
    main = Category.search([('name', '=', category), ('parent_id', '=', False)],
                           limit=1)
    sub = Category.browse()
    if main and subcategory:
        sub = Category.search([('name', '=', subcategory),
                               ('parent_id', '=', main.id)], limit=1)
    kind = _kind(partner, kind_for_person)
    values = {
        'name': project.name,
        'summary': summary,
        'description': project.description or False,
        'partner_id': partner.id,
        'author_id': (lead if partner.is_company and lead else partner).id,
        'kind': kind,
        'category_id': main.id or False,
        'subcategory_id': sub.id or False,
        'city': city or partner.city or '',
        'date_deadline': start - timedelta(days=rnd.randint(4, 30)),
        'funding_rule': 'threshold',
        'funding_threshold': 70,
        'fallback_plan': load_projects._fallback_for({'name': theme}),
        'contribution_basis': _basis(env, partner, kind),
        'required_total': 0,
        'project_id': project.id,
        'state': 'running',
        'import_key': KEY % project.id,
    }
    photo = _main_photo(theme, project.id)
    if photo:
        values['image_1920'] = photo
    return values


def _kind(partner, kind_for_person):
    if not partner.is_company:
        return kind_for_person
    code = partner.coop_legal_form_id.code or ''
    if code in COOP_FORMS:
        return 'cooperative'
    if code in NONPROFIT_FORMS:
        return 'nonprofit'
    return 'commercial'


def _basis(env, partner, kind):
    """Основание денежного вклада — по тому, кто собирает (решения 294, 665)."""
    if kind == 'cooperative' and partner.is_company:
        if len(_members(env, partner)) >= 2:
            return 'share'
        return 'prepay'
    if kind == 'nonprofit':
        if partner.is_company:
            from odoo.addons.coop_projects.models.coop_project import (
                NO_DONATION_FORMS)
            if partner.coop_legal_form_id.code in NO_DONATION_FORMS:
                return 'prepay'
        return 'donation'
    return 'prepay'


def _members(env, org):
    return env['coop.membership'].sudo().search([
        ('organization_id', '=', org.id), ('state', '=', 'active'),
        ('partner_id.is_company', '=', False)]).partner_id


# Формы, которых до № 487 у проектов не было: проект организации такой
# формы стоял на чужой.
LATE_FORMS = ('zao', 'oao', 'artel', 'zhsk', 'gsk', 'skpk', 'union', 'soyuz',
              'tszh', 'tsn', 'snt', 'uchrezhdenie')


def align_economic_forms(env):
    """Форма проекта — по форме инициатора, где справочник её догнал.

    Только демо-проекты и только там, где режим не той формы."""
    Card = env['coop.project'].sudo().with_context(tracking_disable=True)
    Model = env['coop.economic.model'].sudo()
    done = 0
    for card in Card.search(DEMO + [
            ('partner_id.coop_legal_form_id.code', 'in', LATE_FORMS)]):
        form = card.partner_id.coop_legal_form_id
        if card.economic_model_id.legal_form_id == form:
            continue
        models = Model.search([('legal_form_id', '=', form.id)], order='id')
        if models:
            model = models[card.id % len(models)]
            values = {'economic_model_id': model.id}
            if card.economic_scheme_id not in model.scheme_ids:
                values['economic_scheme_id'] = False
            card.write(values)
            done += 1
    _logger.info('Форма проекта по форме инициатора: %s', done)
    return done


def _economic_model(env, card, seed):
    """Экономическая модель — по правовой форме инициатора, у людей — по виду."""
    if card.economic_model_id:
        return
    Model = env['coop.economic.model'].sudo()
    form = card.partner_id.coop_legal_form_id
    models = Model.search([('legal_form_id', '=', form.id)], order='id') \
        if card.partner_id.is_company and form else Model.browse()
    if models:
        card.economic_model_id = models[seed % len(models)].id
        return
    load_projects._set_economic_model(env, card, None, seed)


def _fund(env, card, people, rnd, index, target_state):
    """Вклады до готовности, правдоподобной для этапа, и прочие состояния.

    «Нужно» — сумма потребностей (решение 652); принятые отклики на
    потребности уже в «собрано», здесь добираются вклады без потребности:
    деньги, труд, техника. Признак, что проект уже наполнен, — вклад без
    потребности у карточки.
    """
    Contribution = env['coop.project.contribution'].sudo().with_context(
        tracking_disable=True)
    total = card.required_total
    if not total:
        return 0
    low, high = READINESS.get(target_state or 'running', READINESS['running'])
    goal = total * rnd.randint(low, high) / 100.0
    deficit = goal - card.contribution_total
    today = fields.Date.context_today(card)
    start = card.date_deadline or today
    window_end = today if target_state == 'running' else min(start, today)
    window_start = start - timedelta(days=90)

    def day():
        span = max((window_end - window_start).days, 1)
        return window_start + timedelta(days=rnd.randint(0, span))

    members = Contribution.env['res.partner']
    if card.contribution_basis == 'share' or card._coop_members_only():
        members = _members(env, card.partner_id)
    pool = members or people
    made = 0
    if deficit > 0:
        parts = rnd.choice([2, 3, 3, 4, 4, 5])
        weights = [3.0] + [rnd.uniform(0.6, 1.6) for _ in range(parts - 1)]
        for offset, weight in enumerate(weights):
            kind, title = load_projects.CONTRIBUTION_KINDS[
                (index + offset) % len(load_projects.CONTRIBUTION_KINDS)]
            # Основной вклад — деньгами у шести проектов из семи: вкладка
            # «Финансовые вклады» пуста лишь у тех, кто собрал трудом.
            if offset == 0 and index % 7 != 3:
                kind, title = 'money', 'Денежный взнос'
            value = round(deficit * weight / sum(weights), -2)
            if value <= 0:
                continue
            who = pool[(index * 3 + offset * 11) % len(pool)]
            if who == card.partner_id:
                who = pool[(index * 3 + offset * 11 + 1) % len(pool)]
            accepted = day()
            Contribution.create({
                'project_id': card.id, 'partner_id': who.id, 'kind': kind,
                'name': title, 'value': value, 'state': 'accepted',
                'offered_on': accepted - timedelta(days=rnd.randint(0, 4)),
                'accepted_on': accepted,
            })
            made += 1

    # Другие состояния вклада — чтобы на странице было видно их все.
    extra = []
    if index % 3 == 0:
        extra.append(('offered', 'resource', 'Техника на время работ', 0.06))
    if index % 4 == 1:
        extra.append(('declined', 'labour', 'Смены на площадке', 0.04))
    if index % 5 == 2:
        extra.append(('withdrawn', 'material', 'Материалы', 0.05))
    if target_state in ('frozen', 'cancelled') or index % 9 == 4:
        extra.append(('returned', 'money', 'Денежный взнос', 0.07))
    for step, (state, kind, title, share) in enumerate(extra):
        who = pool[(index * 7 + step * 5 + 3) % len(pool)]
        if who == card.partner_id:
            continue
        offered = day()
        Contribution.create({
            'project_id': card.id, 'partner_id': who.id, 'kind': kind,
            'name': title, 'value': max(round(total * share, -2), 1000),
            'state': state, 'offered_on': offered,
            'accepted_on': offered + timedelta(days=2) if state == 'returned'
            else False,
        })
        made += 1
    return made


def _deals(env, card, index, rnd):
    """Контракты проекта: три из пяти проектов, от одного до трёх.

    Заказчик — инициатор проекта, исполнитель — другая организация.
    """
    if 'coop.deal' not in env or index % 5 in (1, 3):
        return 0
    Deal = env['coop.deal'].sudo().with_context(tracking_disable=True)
    if Deal.search_count([('project_id', '=', card.id)]):
        return 0
    Payment = env['coop.deal.payment'].sudo().with_context(tracking_disable=True)
    orgs = env['res.partner'].sudo().search([('is_company', '=', True)],
                                            order='id', limit=300)
    if len(orgs) < 2:
        return 0
    titles = THEMES[_theme(card.name)][4]
    today = fields.Date.context_today(card)
    total = card.required_total or 300000
    made = 0
    for step in range(rnd.choice([1, 1, 2, 3])):
        side_b = orgs[(index * 7 + step * 3) % len(orgs)]
        if side_b == card.partner_id:
            side_b = orgs[(index * 7 + step * 3 + 1) % len(orgs)]
        state = ('done' if card.project_id.stage_id.name == 'Итоги и распределение'
                 else rnd.choice(load_project_deals.STATE_WEIGHTS))
        signed = (card.date_deadline or today) + timedelta(days=rnd.randint(2, 40))
        if signed > today:
            signed = today - timedelta(days=rnd.randint(1, 20))
        amount = max(round(total * rnd.uniform(0.12, 0.45), -3), 15000)
        deal = Deal.create({
            'name': '%s «%s»' % (titles[step % len(titles)], card.name[:40]),
            'subject': 'project', 'way': 'service',
            'party_a_id': card.partner_id.id, 'party_b_id': side_b.id,
            'role_a': 'заказчик', 'role_b': 'исполнитель',
            'project_id': card.id, 'amount': amount,
            'state': state, 'signed_on': signed,
            'closed_on': signed + timedelta(days=60) if state == 'done' else False,
        })
        Payment.search([('deal_id', '=', deal.id)]).unlink()
        load_project_deals._payments(Payment, deal, rnd, today)
        made += 1
    return made


def _intangible(env, card, index, rnd):
    """Вклад нематериальным активом — у двух проектов из пяти."""
    if 'coop.intangible' not in env or index % 5 not in (0, 2):
        return 0
    Contribution = env['coop.project.contribution'].sudo()
    if Contribution.search_count([('project_id', '=', card.id),
                                  ('intangible_id', '!=', False)]):
        return 0
    assets = env['coop.intangible'].sudo().search(
        [('state', '=', 'active'), ('owner_id', '!=', card.partner_id.id)],
        order='id', limit=400)
    if not assets:
        return 0
    asset = assets[(index * 13 + 7) % len(assets)]
    # Оценка вклада — доля от сметы, а не вся стоимость актива: товарный
    # знак за полмиллиона в проекте на сорок тысяч неправдоподобен
    # (та же причина у `load_intangible_needs`). Вносят право пользования.
    worth = asset.residual_value or asset.initial_cost or 50000
    share = round((card.required_total or 200000) * rnd.uniform(0.06, 0.18), -2)
    contribution = Contribution.create({
        'project_id': card.id, 'partner_id': asset.owner_id.id,
        'kind': 'knowledge', 'name': asset.name,
        'value': max(min(worth, share), 3000),
        'intangible_id': asset.id, 'state': 'offered',
        'offered_on': fields.Date.context_today(card) - timedelta(
            days=rnd.randint(3, 60)),
    })
    if index % 10 != 2:
        contribution.write({'state': 'accepted',
                            'accepted_on': contribution.offered_on})
        contribution._grant_shares()
    return 1


_SUBJECTS = None


def _files(subject):
    global _SUBJECTS
    if _SUBJECTS is None:
        _SUBJECTS = load_media_gallery._index()[0]
    return _SUBJECTS.get(subject) or []


def _read(path):
    with open(path, 'rb') as fh:
        return base64.b64encode(fh.read()).decode()


def _main_photo(theme, seed):
    subjects = THEMES[theme][3]
    for step in range(len(subjects)):
        files = _files(subjects[(seed + step) % len(subjects)])
        if files:
            return _read(files[seed % len(files)])
    return False


def _photos(env, card):
    """Лента фото по теме проекта, а не запасные снимки раздела: у перехода
    на ЭДО не должно быть фото стройки. Сколько — как у остальных
    (`load_media_gallery._want`), главный снимок в счёт."""
    Media = env['coop.media'].sudo()
    theme = _theme(card.name)
    have = Media.search_count([('res_model', '=', 'coop.project'),
                               ('res_id', '=', card.id)])
    need = load_media_gallery._want('coop.project', card.id) - 1 - have
    if need <= 0 or not theme:
        return 0
    subjects = THEMES[theme][3]
    seed = card.project_id.id
    main = subjects[seed % len(subjects)]
    order = [s for s in subjects[seed % len(subjects):] + subjects[:seed % len(subjects)]]
    picked = []
    main_file = (_files(main) or [None])[seed % max(len(_files(main)), 1)]
    for subject in order:
        for path in _files(subject):
            if path != main_file and path not in picked:
                picked.append(path)
                break
        if len(picked) >= need:
            break
    for seq, path in enumerate(picked, have + 2):
        Media.create({'res_model': 'coop.project', 'res_id': card.id,
                      'kind': 'photo', 'sequence': seq,
                      'image_1920': _read(path)})
    return len(picked)

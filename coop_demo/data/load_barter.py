# -*- coding: utf-8 -*-
"""Бартер — объявления и обмены (решение 412, Н7).

Каталог наполняется как действующая площадка:

- около ста семидесяти объявлений — вещи, уже выставленные в «Ресурсах»
  (со снимком оттуда), и около ста пятидесяти — работа, услуги, обучение,
  хендмейд, площади на время, без снимка — значком категории; в каталоге
  «меняю» остаётся около двухсот, остальные — в обмене или обменяны;
- «хочу взамен» — одна-три категории и у половины свои слова;
- обмены во всех состояниях: предложенные (часть — с согласием одной
  стороны), исполняемые (сделки на разных шагах, одна — в споре),
  завершённые (акты, отзывы, история прав ресурса), отклонённые и
  отменённые; полтора десятка — цепочки на троих.

Повторный запуск ничего не добавляет.
"""
import logging
import random
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')

# Рубрика «Ресурсов» → категория обмена.
RESOURCE_CATEGORY = {
    'Оборудование для бизнеса': 'equipment',
    'Грузовики и спецтехника': 'vehicles',
    'Легковые автомобили': 'vehicles',
    'Велосипеды': 'hobby',
    'Ремонт и стройматериалы': 'building',
    'Овощи и фрукты': 'food',
    'Мясная и молочная продукция': 'food',
    'Крупы, мука и бакалея': 'food',
    'Мёд и продукты пчеловодства': 'food',
    'Инструменты': 'tools',
    'Для дома и дачи': 'home',
    'Хобби и отдых': 'hobby',
    'Одежда, обувь, аксессуары': 'clothes',
    'Ноутбуки и компьютеры': 'electronics',
    'Видео и аудио': 'electronics',
    'Оргтехника': 'electronics',
}

# Объявления без ресурса: (категория, заголовок, сколько, оценка от, до).
OWN_OFFERS = [
    ('services', 'Покрою крышу металлочерепицей', 'до 120 м²', 40000, 90000),
    ('services', 'Сварочные работы на выезде', '8 часов', 8000, 16000),
    ('services', 'Вспашу и продискую огород мотоблоком', 'до 15 соток', 3000, 7000),
    ('services', 'Ремонт бензо- и электроинструмента', 'по объёму', 1500, 6000),
    ('services', 'Перевезу груз на «Газели» по области', 'рейс', 4000, 9000),
    ('services', 'Сложу печь-каменку для бани', 'одна печь', 35000, 70000),
    ('services', 'Бухгалтерия ИП на УСН за квартал', 'квартал', 6000, 12000),
    ('services', 'Покраска забора и фасада', 'до 60 м²', 12000, 25000),
    ('services', 'Электромонтаж в частном доме', 'до 10 точек', 10000, 22000),
    ('services', 'Стрижка и уход за садом', 'сезон', 15000, 30000),
    ('services', 'Фотосъёмка мероприятия', '4 часа', 8000, 15000),
    ('services', 'Сайт-визитка для кооператива или фермы', 'под ключ', 20000, 45000),
    ('teaching', 'Уроки английского для школьника', '8 занятий', 6000, 12000),
    ('teaching', 'Научу пчеловодству: сезон с наставником', '6 выездов', 15000, 25000),
    ('teaching', 'Консультация агронома по севообороту', '2 часа', 3000, 6000),
    ('teaching', 'Курс работы на токарном станке', '10 занятий', 12000, 20000),
    ('teaching', 'Репетитор по математике, ОГЭ', '10 занятий', 8000, 15000),
    ('teaching', 'Консультация юриста по договору', '1 час', 2500, 5000),
    ('craft', 'Вязаные шерстяные носки', '5 пар', 2500, 4500),
    ('craft', 'Деревянная посуда ручной работы', 'набор', 3000, 8000),
    ('craft', 'Плетёные корзины из лозы', '3 шт.', 3000, 6000),
    ('craft', 'Керамические кружки ручной лепки', '6 шт.', 4000, 7000),
    ('craft', 'Кованые садовые фонари', '2 шт.', 9000, 18000),
    ('craft', 'Лоскутное одеяло', 'одно', 7000, 14000),
    ('space', 'Гараж с ямой на месяц', 'месяц', 4000, 8000),
    ('space', 'Место на складе под поддоны', '10 паллет на месяц', 6000, 12000),
    ('space', 'Дом у озера на выходные', '2 ночи', 8000, 15000),
    ('space', 'Цех 60 м² с трёхфазным током на неделю', 'неделя', 10000, 20000),
    ('seeds', 'Саженцы яблони, районированные сорта', '10 шт.', 4000, 8000),
    ('seeds', 'Рассада томатов и перца', '60 шт.', 2500, 5000),
    ('seeds', 'Семенной картофель «Гала»', '200 кг', 8000, 14000),
    ('seeds', 'Черенки смородины и крыжовника', '30 шт.', 2000, 4000),
    ('farm', 'Сено в тюках', '100 тюков', 18000, 30000),
    ('farm', 'Зерно фуражное (пшеница)', '1 т', 14000, 20000),
    ('farm', 'Навоз перепревший', '5 т', 5000, 9000),
    ('farm', 'Козье молоко, еженедельно', 'месяц', 6000, 10000),
    ('farm', 'Цыплята-бройлеры суточные', '50 шт.', 4000, 7000),
    ('food', 'Мёд липовый', '20 кг', 12000, 18000),
    ('food', 'Варенье и соленья домашние', '15 банок', 3000, 6000),
    ('food', 'Сыр козий выдержанный', '5 кг', 6000, 10000),
    ('kids', 'Коляска 2 в 1, после одного ребёнка', 'одна', 8000, 16000),
    ('kids', 'Детская одежда 1–3 года, пакетом', '30 вещей', 3000, 6000),
    ('kids', 'Конструктор и развивающие игрушки', 'коробка', 3000, 7000),
    ('clothes', 'Рабочая одежда и спецобувь', '6 комплектов', 6000, 12000),
    ('clothes', 'Зимний пуховик, новый', 'один', 6000, 11000),
    ('hobby', 'Палатка четырёхместная и спальники', 'комплект', 7000, 14000),
    ('hobby', 'Спиннинги и катушки', '3 комплекта', 5000, 12000),
    ('hobby', 'Лодка ПВХ с мотором', 'одна', 45000, 90000),
    ('electronics', 'Ноутбук для учёбы', 'один', 18000, 30000),
    ('electronics', 'Смартфон, в хорошем состоянии', 'один', 9000, 18000),
    ('home', 'Дрова берёзовые колотые', '5 м³', 12000, 18000),
    ('home', 'Стиральная машина, рабочая', 'одна', 6000, 12000),
    ('home', 'Диван раскладной', 'один', 7000, 14000),
    ('building', 'Доска обрезная, остатки со стройки', '2 м³', 20000, 32000),
    ('building', 'Кирпич б/у, очищенный', '1500 шт.', 9000, 15000),
    ('tools', 'Бетономешалка 180 л', 'одна', 9000, 15000),
    ('tools', 'Набор столярного инструмента', 'комплект', 8000, 15000),
    ('equipment', 'Инкубатор на 100 яиц', 'один', 7000, 12000),
    ('equipment', 'Холодильная витрина', 'одна', 20000, 40000),
    ('vehicles', 'Прицеп к легковому автомобилю', 'один', 30000, 55000),
]

WANT_TEXTS = [
    'дрова на зиму', 'помощь с ремонтом крыши', 'саженцы плодовых', 'мёд или сыр',
    'уроки для ребёнка', 'перевозку груза', 'стройматериалы на баню', 'сено для коз',
    'инструмент для огорода', 'детские вещи на вырост', 'ремонт машины', 'место в гараже',
    'электрику в доме', 'зерно для кур', 'ноутбук или планшет', 'рабочую одежду',
]

REVIEW_TEXTS = {
    '5': ['Всё как договаривались, привезли вовремя.', 'Отличный обмен, спасибо!',
          'Вещь в описанном состоянии, человек обязательный.', 'Рекомендую, приятно иметь дело.'],
    '4': ['Всё хорошо, немного задержались с передачей.', 'Нормально, по качеству претензий нет.'],
    '3': ['Обмен состоялся, но договориться о времени было трудно.'],
    '2': ['Состояние хуже, чем на фото. Решили миром.'],
}


def _pick_wants(rnd, own, codes, weights):
    wants = set()
    while len(wants) < rnd.choice([1, 2, 2, 3]):
        code = rnd.choices(codes, weights=weights)[0]
        if code != own:
            wants.add(code)
    return wants


def load_barter(env, login='dashkevich'):
    if 'coop.barter.offer' not in env:
        return 0
    Offer = env['coop.barter.offer'].sudo().with_context(tracking_disable=True,
                                                         mail_create_nolog=True)
    if Offer.search_count([], limit=1):
        _logger.info('Бартер: уже наполнено, пропускаю')
        return 0
    rnd = random.Random(20260925 + 412)
    now = datetime.now().replace(microsecond=0)
    Category = env['coop.barter.category'].sudo()
    cats = {c.code: c for c in Category.search([])}
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True), ('is_company', '=', False),
                             ('name', 'not in', TEST_NAMES)])
    orgs = Partner.search([('coop_is_participant', '=', True), ('is_company', '=', True)])
    orgs = orgs.filtered(lambda p: not (p.name or '').startswith(('ТСЖ', 'ТСН', 'АНО', 'Фонд')))

    # Вещи из «Ресурсов» — со снимком и владельцем.
    Resource = env['coop.resource'].sudo()
    resources = Resource.search([('state', '=', 'published'), ('listing_type', '=', 'offer'),
                                 ('resource_type', 'in', ('material', 'equipment')),
                                 ('owner_id', '!=', False), ('image_1920', '!=', False)])
    resources = [r for r in resources if RESOURCE_CATEGORY.get(r.category_id.name)]
    rnd.shuffle(resources)
    resources = resources[:170]

    codes = list(cats)
    # Чего хотят чаще: еда, дрова, стройка, инструмент, услуги.
    weights = [{'food': 9, 'building': 8, 'services': 9, 'tools': 7, 'home': 7, 'farm': 5,
                'seeds': 5, 'teaching': 4, 'equipment': 4, 'vehicles': 3, 'electronics': 4,
                'kids': 3, 'clothes': 3, 'hobby': 3, 'craft': 2, 'space': 3}.get(c, 2)
               for c in codes]

    def publish_date():
        return now - timedelta(days=rnd.randint(0, 120), hours=rnd.randint(0, 23),
                               minutes=rnd.randint(0, 59))

    made = []
    for resource in resources:
        code = RESOURCE_CATEGORY[resource.category_id.name]
        value = resource.price if resource.price and resource.price < 5_000_000 else \
            rnd.randint(8, 400) * 500
        wants = _pick_wants(rnd, code, codes, weights)
        made.append(Offer.create({
            'name': resource.name,
            'description': 'Выставлено также в «Ресурсах». Посмотреть можно на месте, '
                           'по договорённости.',
            'partner_id': resource.owner_id.id,
            'city': resource.city,
            'category_id': cats[code].id,
            'want_category_ids': [(6, 0, [cats[w].id for w in wants])],
            'want_text': rnd.choice(WANT_TEXTS) if rnd.random() < 0.45 else False,
            'value': round(value, -2),
            'surcharge_ok': rnd.random() < 0.4,
            'condition': 'used' if resource.condition == 'used' else rnd.choice(['new', 'good']),
            'handover_pickup': rnd.random() < 0.85,
            'handover_delivery': rnd.random() < 0.4,
            'handover_post': code in ('electronics', 'clothes', 'hobby', 'tools')
            and rnd.random() < 0.5,
            'resource_id': resource.id,
            'published_on': publish_date(),
        }))

    cities = [c for c in set(people.mapped('city')) if c] or ['Москва']
    for index, (code, title, qty, low, high) in enumerate(OWN_OFFERS):
        for _copy in range(2 if index % 3 else 3):
            partner = rnd.choice(people) if rnd.random() < 0.8 or not orgs else rnd.choice(orgs)
            wants = _pick_wants(rnd, code, codes, weights)
            service = cats[code].is_service
            made.append(Offer.create({
                'name': title,
                'partner_id': partner.id,
                'city': partner.city or rnd.choice(cities),
                'category_id': cats[code].id,
                'want_category_ids': [(6, 0, [cats[w].id for w in wants])],
                'want_text': rnd.choice(WANT_TEXTS) if rnd.random() < 0.5 else False,
                'quantity': qty,
                'value': rnd.randint(low // 100, high // 100) * 100,
                'surcharge_ok': rnd.random() < 0.35,
                'condition': False if service else rnd.choice(['new', 'good', 'used']),
                'handover_pickup': not service or rnd.random() < 0.3,
                'handover_delivery': service or rnd.random() < 0.3,
                'handover_post': code in ('craft', 'clothes', 'kids', 'seeds') and rnd.random() < 0.6,
                'description': False if rnd.random() < 0.4 else
                'Подробности в переписке. Можно частями, можно с доплатой — обсудим.',
                'published_on': publish_date(),
            }))

    # Витрина: у главного участника свои объявления, чтобы «Подходит мне»
    # и «Подобрать обмен» было на чём показать.
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if showcase:
        for offer, wants in ((made[3], ('food', 'services')), (made[-5], ('building', 'tools')),
                             (made[40], ('seeds', 'farm'))):
            offer.write({'partner_id': showcase.partner_id.id,
                         'want_category_ids': [(6, 0, [cats[w].id for w in wants])]})

    exchanges = _load_exchanges(env, rnd, made, now)
    closed = rnd.sample([o for o in made if o.state == 'active'], k=10)
    for offer in closed:
        offer.state = 'closed'
    _logger.info('Бартер: объявлений %s, обменов %s', len(made), exchanges)
    return len(made)


def _load_exchanges(env, rnd, offers, now):
    Exchange = env['coop.barter.exchange'].sudo().with_context(tracking_disable=True,
                                                               mail_create_nolog=True)
    Leg = env['coop.barter.leg'].sudo()
    free = [o for o in offers]
    rnd.shuffle(free)
    plan = (['proposed'] * 18 + ['proposed_half'] * 6 + ['agreed'] * 24 + ['done'] * 32
            + ['declined'] * 9 + ['cancelled'] * 7)
    rnd.shuffle(plan)
    chains_left = 15
    made = 0
    for state in plan:
        size = 3 if chains_left and rnd.random() < 0.18 else 2
        group = []
        while free and len(group) < size:
            offer = free.pop()
            if all(offer.partner_id != other.partner_id for other in group):
                group.append(offer)
        if len(group) < size:
            break
        if size == 3:
            chains_left -= 1
        # Желания сторон подгоняются под обмен: каждый хочет то, что
        # получает, — иначе подбор такой обмен бы не предложил.
        for index, offer in enumerate(group):
            gets = group[index - 1]
            offer.want_category_ids = [(4, gets.category_id.id)]
        started = now - timedelta(days=rnd.randint(2, 100), hours=rnd.randint(0, 20))
        legs = [(offer, group[(index + 1) % len(group)].partner_id)
                for index, offer in enumerate(group)]
        initiator = group[0]
        accepted_all = state in ('agreed', 'done')
        exchange = Exchange.create({
            'kind': 'chain' if size == 3 else 'direct',
            'initiator_id': initiator.partner_id.id,
            'note': rnd.choice([False, False, 'Могу подвезти в субботу.',
                                'Давайте встретимся и посмотрим на месте.',
                                'Если оценки не сойдутся — доплачу разницу.']),
            'leg_ids': [(0, 0, {
                'offer_id': offer.id, 'receiver_id': receiver.id,
                'accepted': accepted_all or offer == initiator
                or (state == 'proposed_half' and index == 1),
                'accepted_on': started + timedelta(hours=index * 7)
                if (accepted_all or offer == initiator
                    or (state == 'proposed_half' and index == 1)) else False,
            }) for index, (offer, receiver) in enumerate(legs)],
        })
        env.cr.execute('UPDATE coop_barter_exchange SET create_date = %s WHERE id = %s',
                       [started, exchange.id])
        made += 1
        if state in ('proposed', 'proposed_half'):
            continue
        if state in ('declined', 'cancelled'):
            exchange.write({'state': state,
                            'closed_on': (started + timedelta(days=rnd.randint(1, 5))).date()})
            continue
        agreed = (started + timedelta(days=rnd.randint(1, 4))).date()
        exchange._coop_make_deals(date=agreed)
        deals = exchange.leg_ids.deal_id
        if state == 'agreed':
            for deal in deals:
                step = rnd.choices(['agreed', 'active', 'acceptance', 'done', 'disputed'],
                                   weights=[25, 35, 20, 15, 5])[0]
                _advance(env, deal, step, agreed, rnd)
            continue
        done_on = agreed + timedelta(days=rnd.randint(2, 20))
        for deal in deals:
            _advance(env, deal, 'done', done_on, rnd)
        exchange.write({'state': 'done', 'closed_on': done_on})
        exchange.leg_ids.offer_id.write({'state': 'done'})
        for deal in deals:
            _review(env, deal, rnd)
    Leg.flush_model()
    return made


def _advance(env, deal, step, when, rnd):
    """Довести сделку обмена до шага — с датами в прошлом."""
    if step == 'agreed':
        return
    if step == 'done':
        closed = when if isinstance(when, date) else when.date()
        # История прав — с датой обмена, а не сегодняшней: запись
        # делается до смены состояния, и крючок сделки её уже не повторит.
        deal._coop_record_rights(date=datetime.combine(closed, datetime.min.time())
                                 + timedelta(hours=rnd.randint(9, 19)))
        deal.write({'state': 'done', 'act_confirmed_a': True, 'act_confirmed_b': True,
                    'act_confirmed_on': closed, 'closed_on': closed})
        (deal.party_a_id | deal.party_b_id)._coop_recompute_deal_stats()
        return
    vals = {'state': step}
    if step == 'acceptance':
        vals['act_confirmed_%s' % rnd.choice('ab')] = True
    if step == 'disputed':
        vals.update({'dispute_opened_by_id': deal.party_b_id.id,
                     'dispute_reason': rnd.choice([
                         'Передали меньше, чем договаривались.',
                         'Состояние заметно хуже, чем в объявлении.',
                         'Сроки сорваны второй раз.'])})
    deal.write(vals)


def _review(env, deal, rnd):
    Review = env['coop.deal.review'].sudo().with_context(tracking_disable=True,
                                                         mail_create_nolog=True)
    for side, author, target in (('a', deal.party_a_id, deal.party_b_id),
                                 ('b', deal.party_b_id, deal.party_a_id)):
        if rnd.random() < 0.2:
            continue
        rating = rnd.choices(['5', '4', '3', '2'], weights=[62, 25, 9, 4])[0]
        Review.create({'deal_id': deal.id, 'author_id': author.id, 'target_id': target.id,
                       'side': side, 'rating': rating,
                       'body': rnd.choice(REVIEW_TEXTS[rating])})

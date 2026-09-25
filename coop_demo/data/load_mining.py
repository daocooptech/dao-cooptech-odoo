# -*- coding: utf-8 -*-
"""Майнеры и биржа майнинговых мощностей (решение 392, разбор юриста 2.4).

Каталоги наполняются не менее чем сотней-двумя примеров: здесь сто
десять майнеров и сто тридцать предложений. Раскладка неровная:

- юрлица, ИП и физлица без ИП; у юрлиц и ИП — запись в реестре ФНС или
  заявление на рассмотрении, у части — записи нет (это видно
  предупреждением); физлица в основном в пределах лимита, несколько — сверх;
- площадки у ГЭС, на попутном газе, от сети; от гаража на 5 кВт до
  промышленных 2 МВт;
- предложения: размещение оборудования, аренда асиков, аренда хешрейта,
  ремонт; предлагают и ищут; часть — снятые.

Повторный запуск ничего не добавляет.
"""
import logging
import random
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

TEST_NAMES = ('Danil', 'Proverka Vyhoda',
              'Игнатьев Денис Олегович', 'Прохорова Вера Андреевна')

# Город, регион, основной источник энергии.
SITES = [
    ('Иркутск', 'Иркутская область', 'hydro'), ('Братск', 'Иркутская область', 'hydro'),
    ('Красноярск', 'Красноярский край', 'hydro'), ('Саяногорск', 'Республика Хакасия', 'hydro'),
    ('Абакан', 'Республика Хакасия', 'hydro'), ('Кемерово', 'Кемеровская область', 'grid'),
    ('Новосибирск', 'Новосибирская область', 'grid'), ('Омск', 'Омская область', 'grid'),
    ('Тюмень', 'Тюменская область', 'gas'), ('Сургут', 'ХМАО — Югра', 'gas'),
    ('Нижневартовск', 'ХМАО — Югра', 'gas'), ('Пермь', 'Пермский край', 'grid'),
    ('Екатеринбург', 'Свердловская область', 'grid'), ('Тверь', 'Тверская область', 'grid'),
    ('Волгоград', 'Волгоградская область', 'solar'), ('Краснодар', 'Краснодарский край', 'solar'),
]

EQUIPMENT = [
    ('Antminer S21', 200, 3500), ('Antminer S19k Pro', 120, 2760),
    ('Whatsminer M60S', 186, 3420), ('Whatsminer M50', 118, 3300),
    ('Avalon A1466', 150, 3230), ('Antminer L7 (LTC/DOGE)', 9.5, 3425),
]

OFFER_TITLES = {
    'hosting': ['Место под {n} асиков у ГЭС', 'Размещение оборудования, контейнер {n} мест',
                'Хостинг асиков, промплощадка {n} мест', 'Место в гараже под {n} устройств'],
    'equipment': ['Сдам в аренду {n} × Antminer S19k Pro', 'Аренда асиков Whatsminer, {n} шт.',
                  'Ищу в аренду {n} устройств на сезон'],
    'hashrate': ['Аренда хешрейта {n} TH/s', 'Продам мощность {n} TH/s на месяц'],
    'service': ['Ремонт плат хеширования', 'Прошивка и настройка асиков',
                'Обслуживание майнинговой фермы под ключ'],
}


def load_mining(env, login='dashkevich', miners=110, offers=130):
    if 'coop.miner' not in env:
        return 0
    Miner = env['coop.miner'].sudo().with_context(tracking_disable=True, mail_create_nolog=True)
    Offer = env['coop.mining.offer'].sudo().with_context(tracking_disable=True, mail_create_nolog=True)
    if Miner.search_count([], limit=1):
        _logger.info('Майнинг: уже наполнено, пропускаю')
        return 0
    rnd = random.Random(20260925 + 3923)
    today = date.today()
    now = datetime.now().replace(microsecond=0)
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True), ('is_company', '=', False),
                             ('name', 'not in', TEST_NAMES)])
    orgs = Partner.search([('coop_is_participant', '=', True), ('is_company', '=', True)])
    orgs = orgs.filtered(lambda p: not (p.name or '').startswith(('ТСЖ', 'ТСН', 'АНО', 'Фонд')))
    candidates = list(rnd.sample(list(orgs), k=min(40, len(orgs)))) + \
        list(rnd.sample(list(people), k=min(miners, len(people))))
    rnd.shuffle(candidates)

    made = []
    for index, partner in enumerate(candidates[:miners]):
        if partner.is_company:
            kind = 'legal'
        else:
            kind = rnd.choices(['ip', 'person'], weights=[35, 65])[0]
        city, region, energy = rnd.choice(SITES)
        model, ths, watts = rnd.choice(EQUIPMENT)
        if kind == 'legal':
            count = rnd.randint(40, 600)
        elif kind == 'ip':
            count = rnd.randint(8, 120)
        else:
            count = rnd.choice([1, 1, 1, 2, 2, 2, 3])
        power = max(1, round(count * watts / 1000))
        monthly = power * 24 * 30
        if kind == 'person':
            # Сверх лимита физлицу реестр не «не нужен» — нужен ИП и запись.
            registry = 'not_required' if monthly <= 6000 else 'missing'
        else:
            registry = rnd.choices(['registered', 'pending', 'missing'], weights=[72, 18, 10])[0]
        vals = {
            'partner_id': partner.id,
            'kind': kind,
            'registry_state': registry,
            'city': city,
            'region': region,
            'energy_source': energy if kind != 'person' else rnd.choice(['grid', 'grid', energy]),
            'power_kw': power,
            'monthly_kwh': monthly,
            'hashrate': round(count * ths, 1),
            'equipment': '%s × %d' % (model, count),
            'coins': 'LTC, DOGE' if 'L7' in model else rnd.choice(['BTC', 'BTC', 'BTC, BCH']),
            'restricted_region': region == 'Иркутская область' and rnd.random() < 0.3,
        }
        if registry == 'registered':
            vals['registry_number'] = '%02d%s-%06d' % (rnd.randint(1, 89), rnd.choice('МИО'),
                                                       rnd.randint(1000, 999999))
            vals['registry_date'] = today - timedelta(days=rnd.randint(30, 600))
        made.append(Miner.create(vals))

    for index in range(offers):
        kind = rnd.choices(['hosting', 'equipment', 'hashrate', 'service'],
                           weights=[40, 25, 20, 15])[0]
        miner = rnd.choice(made)
        side = 'request' if (kind == 'equipment' and rnd.random() < 0.3) or rnd.random() < 0.12 else 'offer'
        n = rnd.choice([5, 10, 20, 40, 80, 150, 300])
        titles = [t for t in OFFER_TITLES[kind]
                  if 'ГЭС' not in t or miner.energy_source == 'hydro']
        title = rnd.choice(titles).format(n=n)
        if kind == 'hosting':
            price, unit, cap, cap_unit = round(rnd.uniform(3.8, 6.5), 2), 'kwh', n, 'places'
        elif kind == 'equipment':
            price, unit, cap, cap_unit = rnd.randint(4, 14) * 500, 'device_month', n, 'devices'
        elif kind == 'hashrate':
            price, unit, cap, cap_unit = round(rnd.uniform(4.5, 9.0), 2), 'ths_day', n * 10, 'ths'
        else:
            price, unit, cap, cap_unit = rnd.randint(15, 40) * 100, 'hour', 0, 'devices'
        Offer.create({
            'name': title,
            'side': side,
            'kind': kind,
            'miner_id': miner.id,
            'author_id': miner.partner_id.id,
            'city': miner.city,
            'capacity': cap,
            'capacity_unit': cap_unit,
            'price': price if rnd.random() > 0.08 else 0,
            'price_unit': unit,
            'min_term': rnd.choice(['1 месяц', '3 месяца', '6 месяцев', '', '']) or False,
            'infra_registered': kind == 'hosting' and miner.kind == 'legal'
            and miner.registry_state == 'registered',
            'description': 'Круглосуточная охрана, видеонаблюдение, выход на связь в течение '
                           'часа. Договор аренды, акты ежемесячно.' if kind == 'hosting' else False,
            'state': 'closed' if rnd.random() < 0.1 else 'published',
            'published_on': now - timedelta(days=rnd.randint(0, 90), hours=rnd.randint(0, 23)),
        })

    _logger.info('Майнинг: майнеров %s, предложений %s', len(made), offers)
    return len(made)


def repair_mining_titles(env):
    """«У ГЭС» — только у площадок на ГЭС.

    Первый прогон брал заголовок наугад, и «Место под 5 асиков у ГЭС»
    стояло в Кемерово с питанием от сети. Повторный запуск ничего не меняет.
    """
    if 'coop.mining.offer' not in env:
        return 0
    wrong = env['coop.mining.offer'].sudo().with_context(tracking_disable=True).search([
        ('name', 'ilike', ' у ГЭС'), ('energy_source', '!=', 'hydro')])
    for offer in wrong:
        offer.name = offer.name.replace(' у ГЭС', '')
    if wrong:
        _logger.info('Майнинг: «у ГЭС» снято у %s предложений', len(wrong))
    # Физлицо сверх лимита стояло «не требуется — в пределах лимита».
    over = env['coop.miner'].sudo().search([
        ('kind', '=', 'person'), ('monthly_kwh', '>', 6000),
        ('registry_state', '=', 'not_required')])
    over.write({'registry_state': 'missing'})
    if over:
        _logger.info('Майнинг: физлиц сверх лимита без записи — %s', len(over))
    return len(wrong) + len(over)

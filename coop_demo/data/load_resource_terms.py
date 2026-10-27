# -*- coding: utf-8 -*-
"""Условия объявлений по способам передачи (решение 412, Н5).

Строки условий заводит сам модуль ресурсов — по одной на отмеченный
способ; здесь они заполняются так, как заполнил бы владелец: у продажи —
цена и как платить, у аренды — цена за сутки или месяц, залог и срок, у
обмена — что возьмёт взамен, у безвозмездной передачи — как забрать.
Заполняются только пустые строки: то, что написал человек, не трогаем, и
повторный запуск ничего не меняет.
"""
import datetime
import logging
import random
import re

_logger = logging.getLogger(__name__)

SALE_NOTES = ['оплата при получении', 'самовывоз, погрузим сами', 'наличными или переводом',
              'доставка по городу от двух единиц', 'предоплата 50 %, остальное при получении',
              'чек и документы на руки', 'можно частями']
BUY_NOTES = ['рассмотрю б/у в хорошем состоянии', 'заберу сам', 'оплата сразу',
             'нужно к концу месяца', 'интересует партия, не штучно']
RENT_TERMS = ['1 сутки', '2 суток', '3 суток', 'неделя']
RENT_NOTES = ['паспорт и договор', 'доставка за ваш счёт', 'с оператором — за доплату',
              'выдаём после инструктажа', 'возврат чистым', 'на выходные — скидка']
INSTALLMENT = [('3 месяца', 'первый взнос 30 %'), ('6 месяцев', 'первый взнос 20 %'),
               ('12 месяцев', 'первый взнос 40 %, по договору')]
LEASING = [('12–36 месяцев', 'аванс 20 %, через лизинговую компанию'),
           ('24 месяца', 'аванс 15 %, выкуп в конце срока')]
PROJECT_NOTES = ['вношу как вклад по оценке, доля по договору',
                 'в проект кооператива, отчёт по использованию',
                 'на время проекта, потом возврат']
BARTER_NOTES = ['на стройматериалы', 'на инструмент или технику', 'на корма или зерно',
                'на мёд, сыр, домашние продукты', 'на помощь с ремонтом', 'на дрова',
                'на саженцы и рассаду', 'предложите — обсудим']
FREE_NOTES = ['забрать самому до конца месяца', 'только своим транспортом',
              'отдам тому, кому нужнее', 'самовывоз, помогу погрузить']

SPACE_NOTES = ['коммунальные включены', 'свет по счётчику', 'доступ круглосуточно',
               'охрана и видеонаблюдение']
RENT_UNITS = ('сутки', 'день', 'смена', 'час', 'месяц', 'неделя', 'выходные')

MONTHLY_WORDS = ('дом', 'дача', 'квартир', 'гараж', 'склад', 'помещен', 'участ', 'цех')


def _money(value, step=100):
    return round(value / step) * step


def _rent_priced(resource):
    name = (resource.name or '').lower()
    return name.startswith(('сдам', 'сдаю', 'аренда', 'прокат')) or         (resource.price_unit_label or '').lower() in RENT_UNITS


def _value_of(resource):
    """Оценка вещи по арендной цене: сутки — примерно два месяца
    аренды, месяц — два года."""
    per = 24 if (resource.price_unit_label or '').lower() == 'месяц' else 60
    return _money((resource.price or 0) * per, 1000)


def repair_resource_terms(env):
    """Первое заполнение (`91c5b63`) ставило продаже, рассрочке и лизингу
    арендную цену («12 000 ₽ за сутки»), а аренде помещений — «договор от
    полугода» при сроке в месяц. Правит только такие строки; повторный
    запуск ничего не меняет."""
    if 'coop.resource.term' not in env:
        return 0
    Term = env['coop.resource.term'].sudo()
    fixed = 0
    for term in Term.search([('code', 'in', ('sale', 'installment', 'leasing', 'project'))]):
        resource = term.resource_id
        if not _rent_priced(resource) or not resource.price:
            continue
        if term.price == resource.price or (term.price_unit_label or '').lower() in RENT_UNITS:
            term.write({'price': _value_of(resource),
                        'price_unit_label': resource.uom_label or False})
            fixed += 1
    odd = Term.search([('code', '=', 'rent'), ('note', '=', 'договор от полугода'),
                       ('min_term', '!=', 'полгода')])
    odd.write({'note': 'свет по счётчику'})
    fixed += len(odd)
    if fixed:
        _logger.info('Ресурсы: условия поправлены у %s строк', fixed)
    return fixed


def fill_resource_terms(env):
    if 'coop.resource.term' not in env:
        return 0
    Term = env['coop.resource.term'].sudo()
    # Строки, заведённые до наполнения, — у всех объявлений со способами.
    env['coop.resource'].sudo().with_context(active_test=False).search(
        [('method_ids', '!=', False), ('term_ids', '=', False)])._coop_sync_terms()
    empty = Term.search([]).filtered(lambda t: not (t.price or t.deposit or t.min_term
                                                    or t.note or t.price_unit_label))
    filled = 0
    for term in empty:
        # Жребий — от объявления и способа, а не от номера строки: строку
        # пересоздаёт смена способов, и текст не должен от этого меняться.
        rnd = random.Random("%s:%s" % (term.resource_id.id, term.code))
        resource = term.resource_id
        code = term.code
        base = resource.price or 0
        unit = resource.price_unit_label or resource.uom_label or ''
        if code != 'rent' and _rent_priced(resource):
            # Цена объявления арендная («12 000 ₽ за сутки»): продажа,
            # рассрочка и лизинг — от оценки самой вещи, а не от суток.
            base, unit = _value_of(resource), resource.uom_label or ''
        request = resource.listing_type == 'request'
        vals = {}
        if code == 'sale':
            vals = {'price': base, 'price_unit_label': unit,
                    'note': rnd.choice(BUY_NOTES if request else SALE_NOTES)}
        elif code == 'rent':
            name = (resource.name or '').lower()
            monthly = any(w in name for w in MONTHLY_WORDS)
            # У «Сдам…» цена в объявлении уже арендная; у вещи на продажу
            # аренда считается от её цены.
            if _rent_priced(resource) and base:
                price = base
                unit = resource.price_unit_label or ('месяц' if monthly else 'сутки')
            else:
                value = base or rnd.randint(20, 400) * 1000
                price = max(500, _money(value * (0.06 if monthly else 0.02)))
                unit = 'месяц' if monthly else 'сутки'
            vals = {'price': price, 'price_unit_label': unit,
                    'deposit': 0 if request else _money(
                        price * (1 if monthly else rnd.choice([2, 3, 5])), 500),
                    'min_term': rnd.choice(['1 месяц', '3 месяца', 'полгода']) if monthly
                    else rnd.choice(RENT_TERMS),
                    'note': rnd.choice(SPACE_NOTES if monthly else RENT_NOTES)}
        elif code == 'installment':
            term_len, note = rnd.choice(INSTALLMENT)
            vals = {'price': base, 'price_unit_label': unit, 'min_term': term_len, 'note': note}
        elif code == 'leasing':
            term_len, note = rnd.choice(LEASING)
            vals = {'price': base, 'min_term': term_len, 'note': note}
        elif code == 'project':
            vals = {'price': base, 'note': rnd.choice(PROJECT_NOTES)}
        elif code == 'barter':
            vals = {'note': rnd.choice(BARTER_NOTES)}
        elif code == 'free':
            vals = {'note': rnd.choice(FREE_NOTES)}
        if vals:
            term.write(vals)
            filled += 1
    if filled:
        _logger.info('Ресурсы: условия по способам заполнены у %s строк', filled)
    return filled


# Поля способов (решение 629): то, что написал бы владелец объявления. Около
# каждой седьмой строки оставляем без подробностей — так и бывает.
WARRANTY = ['6 месяцев', '1 год', '3 месяца', '2 года', '14 дней на проверку']
LONG_DISCOUNT = ['от недели — 10 %', 'от месяца — 15 %', 'от трёх дней — 5 %', 'от месяца — 20 %']
OPERATOR_WORDS = ('экскаватор', 'погрузчик', 'трактор', 'кран', 'манипулятор', 'самосвал',
                  'бульдозер', 'автовышк', 'каток', 'грейдер', 'фронтальн')
LESSORS = ['«Сбербанк Лизинг»', '«Европлан»', '«Росагролизинг»', '«Балтийский лизинг»',
           '«Альфа-Лизинг»', '«Газпромбанк Автолизинг»']
SCOPES = ['любые', 'стройка и ремонт', 'фермерские проекты', 'проекты кооператива',
          'мастерские и производство', 'в своём городе', 'экологические проекты']


def _first_int(text, default=0):
    found = re.findall(r'\d+', text or '')
    if not found:
        return default
    numbers = [int(n) for n in found[:2]]
    return round(sum(numbers) / len(numbers))


def fill_term_details(env):
    """Заполняет поля способов у строк, где их ещё нет; повторный запуск
    ничего не меняет, написанное человеком не трогает."""
    if 'coop.resource.term' not in env or 'months' not in env['coop.resource.term']._fields:
        return 0
    Term = env['coop.resource.term'].sudo()
    today = datetime.date.today()
    filled = 0
    for term in Term.search([]):
        if any(term[f] for f in ('min_qty', 'prepay_pct', 'warranty', 'documents', 'max_term',
                                 'operator', 'included', 'available_from', 'months', 'ownership',
                                 'lessor', 'contribution', 'expect', 'surcharge', 'free_mode')):
            continue
        rnd = random.Random("details:%s:%s" % (term.resource_id.id, term.code))
        if rnd.random() < 0.14:
            continue
        resource = term.resource_id
        request = resource.listing_type == 'request'
        name = (resource.name or '').lower()
        is_org = bool(resource.owner_id.is_company) if 'is_company' in resource.owner_id._fields else False
        code = term.code
        vals = {}
        if code == 'sale':
            unit = (term.price_unit_label or '').lower()
            bulk = unit in ('кг', 'т', 'м³', 'м²', 'м', 'шт.', 'шт', 'мешок', 'литр', 'л')
            if bulk and rnd.random() < 0.6:
                vals['min_qty'] = rnd.choice([5, 10, 20, 50, 100])
                if not request and term.price and rnd.random() < 0.5:
                    vals['bulk_qty'] = vals['min_qty'] * rnd.choice([5, 10])
                    vals['bulk_price'] = _money(term.price * rnd.choice([0.85, 0.9, 0.93]), 10)
            if rnd.random() < 0.35:
                vals['prepay_pct'] = rnd.choice([30, 50, 100])
            if not request and resource.resource_type in ('material', 'equipment') and rnd.random() < 0.4 \
                    and resource.condition != 'used':
                vals['warranty'] = rnd.choice(WARRANTY)
            vals['documents'] = 'upd' if is_org and rnd.random() < 0.8 else \
                rnd.choice(['receipt', 'receipt', 'none'])
        elif code == 'rent':
            heavy = any(w in name for w in OPERATOR_WORDS)
            if heavy:
                vals['operator'] = rnd.choice(['yes', 'option', 'no'])
                vals['included'] = rnd.choice(['топливо', 'топливо, доставка', 'доставка', False])
            elif rnd.random() < 0.4:
                vals['included'] = rnd.choice(['расходники', 'доставка', 'расходники, доставка'])
            if not request and rnd.random() < 0.5:
                monthly = (term.price_unit_label or '') == 'месяц'
                vals['max_term'] = rnd.choice(['год', '11 месяцев', '3 года']) if monthly \
                    else rnd.choice(['2 недели', 'месяц', '2 месяца'])
            if rnd.random() < 0.55:
                vals['available_from'] = today + datetime.timedelta(
                    days=rnd.choice([0, 1, 3, 7, 10, 14, 21, 30, 45]))
            if not request and rnd.random() < 0.3:
                vals['long_discount'] = rnd.choice(LONG_DISCOUNT)
        elif code == 'installment':
            vals = {'months': _first_int(term.min_term, 6) or 6,
                    'down_pct': _first_int(term.note, 20),
                    'pay_every': 'month' if rnd.random() < 0.85 else rnd.choice(['week', 'quarter']),
                    'markup_pct': 0 if rnd.random() < 0.6 else rnd.choice([3, 5, 8, 10]),
                    'ownership': 'end' if rnd.random() < 0.6 else 'now'}
        elif code == 'leasing':
            months = _first_int(term.min_term, 24) or 24
            partner = 'компани' in (term.note or '') or rnd.random() < 0.5
            vals = {'months': months, 'down_pct': _first_int(term.note, 15),
                    'markup_pct': rnd.choice([8, 10, 12, 15]),
                    'buyout': _money((term.price or 0) * rnd.choice([0.01, 0.05, 0.1]), 1000),
                    'insurance': rnd.choice(['lessee', 'lessee', 'lessor'])}
            if not request:
                vals['lessor'] = 'partner' if partner else 'self'
                if partner:
                    vals['lessor_name'] = rnd.choice(LESSORS)
        elif code == 'project':
            vals = {'contribution': 'use' if 'возврат' in (term.note or '') or rnd.random() < 0.4
                    else 'own',
                    'expect': rnd.choice(['share', 'share', 'product', 'costs']),
                    'project_scope': rnd.choice(SCOPES)}
        elif code == 'barter':
            roll = rnd.random()
            vals['surcharge'] = 'none' if roll < 0.6 else ('pay' if roll < 0.8 else 'want')
            if vals['surcharge'] != 'none':
                vals['surcharge_amount'] = _money(max(500, (term.price or 20000) * rnd.choice([0.1, 0.2, 0.3])), 500)
        elif code == 'free':
            vals = {'free_mode': 'loan' if rnd.random() < 0.2 else 'forever'}
            if not request:
                vals['free_to'] = rnd.choice(['any', 'any', 'any', 'org', 'project'])
        if vals:
            term.write(vals)
            filled += 1
    filled += tidy_term_details(env)
    if filled:
        _logger.info('Ресурсы: поля способов заполнены у %s строк', filled)
    return filled


GENERATED_NOTES = {note for _len, note in INSTALLMENT + LEASING}


def tidy_term_details(env):
    """Текст первого наполнения повторял то, что теперь в полях: «первый
    взнос 30 %», «аванс 20 %, через лизинговую компанию», «с оператором —
    за доплату». Снимает только такой текст; написанное человеком — нет."""
    Term = env['coop.resource.term'].sudo()
    tidied = 0
    for term in Term.search([('code', 'in', ('installment', 'leasing')), ('months', '>', 0)]):
        vals = {}
        if term.min_term:
            vals['min_term'] = False
        if term.note in GENERATED_NOTES:
            vals['note'] = False
        if vals:
            term.write(vals)
            tidied += 1
    plain = [n for n in RENT_NOTES if 'оператор' not in n]
    for term in Term.search([('code', '=', 'rent'), ('operator', '!=', False),
                             ('note', '=', 'с оператором — за доплату')]):
        term.note = random.Random("tidy:%s" % term.resource_id.id).choice(plain)
        tidied += 1
    return tidied


# Проверки публикации по разборам агентов 27.10.2026 (решение 629): чего
# требует `_coop_terms_problems`, то у опубликованных демо-объявлений есть.
VEHICLE_WORDS = ('автомоб', 'самосвал', 'кран', 'манипулятор', 'грузов', 'тягач', 'автобус',
                 'фургон', 'газел', 'трактор', 'прицеп', 'мотоцикл', 'квадроцикл')
SELLERS = ['ООО «СибТехТорг»', 'ООО «Агротехника-Центр»', 'дилер «Ростсельмаш»',
           'ООО «Спецмаш-Урал»', 'ООО «ТехноПарк Поволжье»', 'завод-изготовитель']
WEAR = ['царапины и потёртости корпуса', 'пробег до 5 000 км в месяц',
        'износ режущих частей, заточка за проектом', 'следы работы, без поломок',
        'моточасы по счётчику, до 150 в месяц']


def fill_term_checks(env):
    """Дозаполняет то, без чего объявление теперь не опубликовать; написанное
    человеком не трогает, повторный запуск ничего не меняет."""
    if 'coop.resource.term' not in env or 'seller_name' not in env['coop.resource.term']._fields:
        return 0
    Term = env['coop.resource.term'].sudo()
    fixed = 0
    for term in Term.search([]):
        resource = term.resource_id
        if resource.listing_type == 'request':
            continue
        rnd = random.Random("checks:%s:%s" % (resource.id, term.code))
        company = resource.owner_id.is_company
        name = (resource.name or '').lower()
        vals = {}
        if term.code == 'sale' and company:
            if not term.documents or term.documents == 'none':
                vals['documents'] = rnd.choice(['upd', 'upd', 'upd', 'receipt', 'act'])
            if not term.vat:
                vals['vat'] = rnd.choice(['none', 'none', '22', '22', '5', '7'])
        elif term.code == 'rent' and term.operator in ('yes', 'option') and not term.is_vehicle:
            vals['is_vehicle'] = 'yes' if any(w in name for w in VEHICLE_WORDS) else 'no'
        elif term.code == 'leasing' and term.lessor == 'self' and not term.seller_name:
            vals['seller_name'] = rnd.choice(SELLERS)
        elif term.code == 'installment' and not (term.months > 0 and term.pay_every):
            vals = {'months': term.months or rnd.choice([3, 6, 12]), 'pay_every': term.pay_every or 'month'}
        elif term.code == 'project' and term.contribution == 'use':
            base = term.price or resource.price or 60000
            if not term.months:
                vals['months'] = rnd.choice([3, 6, 12])
            if not term.use_rate:
                vals['use_rate'] = _money(base * rnd.choice([0.03, 0.04, 0.05]), 100) or 1000
            if not term.repairs:
                vals['repairs'] = rnd.choice(['project', 'project', 'owner'])
            if not term.wear:
                vals['wear'] = rnd.choice(WEAR)
            if not term.loss:
                vals['loss'] = rnd.choice(['compensate', 'compensate', 'own'])
        elif term.code == 'free' and term.free_to == 'org' and not term.price:
            vals['price'] = _money(rnd.randint(3, 60) * 1000, 500)
        elif term.code == 'barter' and company and not term.price and term.price_kind != 'none':
            vals['price'] = _money(rnd.randint(5, 120) * 1000, 500)
        if vals:
            term.write(vals)
            fixed += 1
    if fixed:
        _logger.info('Ресурсы: условия дозаполнены под проверки публикации у %s строк', fixed)
    return fixed

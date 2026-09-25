# -*- coding: utf-8 -*-
"""Условия объявлений по способам передачи (решение 412, Н5).

Строки условий заводит сам модуль ресурсов — по одной на отмеченный
способ; здесь они заполняются так, как заполнил бы владелец: у продажи —
цена и как платить, у аренды — цена за сутки или месяц, залог и срок, у
обмена — что возьмёт взамен, у безвозмездной передачи — как забрать.
Заполняются только пустые строки: то, что написал человек, не трогаем, и
повторный запуск ничего не меняет.
"""
import logging
import random

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
        rnd = random.Random(20260925 + term.id)
        resource = term.resource_id
        base = resource.price or 0
        unit = resource.price_unit_label or resource.uom_label or ''
        if code != 'rent' and _rent_priced(resource):
            # Цена объявления арендная («12 000 ₽ за сутки»): продажа,
            # рассрочка и лизинг — от оценки самой вещи, а не от суток.
            base, unit = _value_of(resource), resource.uom_label or ''
        request = resource.listing_type == 'request'
        vals = {}
        code = term.code
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

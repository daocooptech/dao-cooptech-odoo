# -*- coding: utf-8 -*-
"""Добор примеров: по 25 на каждый случай.

Требование владельца: у каждого сценария должно быть не меньше 25
примеров. Причина простая и проверяемая: на трёх записях не видно ни
сортировки, ни фильтра, ни поведения экрана под нагрузкой, а состояние,
которого в данных нет вовсе, нельзя ни показать, ни проверить. Отклонённый
банком вывод, отклонённая сетью транзакция, круг взаимозачёта, который
никто не подписал, — всё это экраны, которые иначе никто не увидит до
боевой эксплуатации.

Загрузчик добирает, а не пересоздаёт: считает, сколько случаев уже есть,
и дописывает недостающие. Повторный прогон ничего не удваивает.
"""
import logging
import random

from odoo import fields

from . import load_wallets

_logger = logging.getLogger(__name__)

TARGET = 25

# Сетевые операции: что бывает в блокчейн-кошельке.
TX_ASSETS = [
    ('btc', 'BTC', 0.004, 0.09, 7_270_000),
    ('eth', 'ETH', 0.05, 2.4, 221_000),
    ('eth', 'USDT', 50, 1200, 90),
    ('ton', 'TON', 20, 600, 330),
    ('sol', 'SOL', 1.0, 20, 9_000),
    ('koop', 'КООП', 100, 5000, 10),
]


def load_examples(env):
    made = {}
    made.update(_fiat_cases(env))
    made.update(_crypto_cases(env))
    made.update(_credit_cases(env))
    made.update(_clearing_cases(env))
    made.update(_share_cases(env))
    made.update(_deal_cases(env))
    made.update(_payment_cases(env))
    made.update(_review_cases(env))
    made.update(_token_cases(env))
    made.update(_verification_cases(env))
    made.update(_application_cases(env))
    made.update(_friendship_cases(env))
    made.update(_contribution_cases(env))
    made.update(_project_state_cases(env))
    made.update(_outcome_cases(env))
    _logger.info('Добор примеров по случаям: %s', made)
    return True


def _need(env, model, domain):
    """Сколько записей не хватает до двадцати пяти."""
    return max(0, TARGET - env[model].sudo().search_count(domain))


def _rnd():
    # Одно и то же зерно: разница между двумя прогонами должна означать
    # изменение данных, а не случайность.
    return random.Random(20260902)


# ── Кошелёк: фиат ───────────────────────────────────────────────────────

def _fiat_cases(env):
    Movement = env['coop.wallet.movement'].sudo()
    Wallet = env['coop.wallet'].sudo()
    wallets = Wallet.search([('method_ids', '!=', False)], limit=60)
    if not wallets:
        return {}
    rnd = _rnd()
    made = {}

    for kind, state, title in (
        ('correction', 'confirmed', 'Корректировка по акту сверки'),
        ('transfer', 'cancelled', 'Перевод участнику — отменён до отправки'),
    ):
        need = _need(env, 'coop.wallet.movement',
                     [('kind', '=', kind), ('state', '=', state)])
        for index in range(need):
            wallet = wallets[index % len(wallets)]
            Movement.create({
                'wallet_id': wallet.id,
                'date': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'name': title,
                'kind': kind,
                'amount': rnd.choice([-1, 1]) * rnd.randint(1500, 40000),
                'state': state,
            })
        made['фиат %s/%s' % (kind, state)] = need
    return made


# ── Кошелёк: сетевые операции ───────────────────────────────────────────

def _crypto_cases(env):
    Tx = env['coop.wallet.tx'].sudo()
    Wallet = env['coop.wallet'].sudo()
    Network = env['coop.wallet.network'].sudo()
    Partner = env['res.partner'].sudo()

    networks = {n.code: n for n in Network.with_context(active_test=False).search([])}
    wallets = Wallet.search([('asset_ids', '!=', False)], limit=60)
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=40)
    if not networks or not wallets:
        return {}

    rnd = _rnd()
    made = {}
    cases = [
        ('in', 'confirmed'), ('out', 'confirmed'), ('swap', 'confirmed'),
        ('fee', 'confirmed'), ('out', 'pending'), ('out', 'failed'),
    ]
    for kind, state in cases:
        need = _need(env, 'coop.wallet.tx',
                     [('kind', '=', kind), ('state', '=', state)])
        for index in range(need):
            wallet = wallets[index % len(wallets)]
            code, symbol, low, high, rate = TX_ASSETS[index % len(TX_ASSETS)]
            network = networks.get(code)
            if not network:
                continue
            quantity = round(rnd.uniform(low, high), 8)
            sign = 1 if kind == 'in' else -1
            values = {
                'wallet_id': wallet.id,
                'network_id': network.id,
                'date': '2026-%02d-%02d %02d:%02d:00' % (
                    1 + index % 9, 1 + index % 27, index % 24, (index * 7) % 60),
                'kind': kind,
                'symbol': symbol,
                'quantity': sign * quantity,
                'valuation': round(quantity * rate),
                'tx_hash': load_wallets.tx_hash_for(code, index * 104729 + 7),
                'state': state,
            }
            if kind == 'fee':
                values['quantity'] = -round(quantity / 400, 8)
                values['valuation'] = round(values['quantity'] * rate)
            if kind == 'swap':
                # Обмен — одна операция с двумя ногами. Вторая нога своим
                # полем: двумя строками потом не восстановить, что это был
                # один акт.
                other_code, other_symbol, o_low, o_high, _rate = TX_ASSETS[
                    (index + 3) % len(TX_ASSETS)]
                values['swap_symbol'] = other_symbol
                values['swap_quantity'] = round(rnd.uniform(o_low, o_high), 8)
                values['swap_network_id'] = networks.get(
                    other_code, network).id
            # У части операций вторая сторона — участник платформы: по
            # внешнему адресу человека не узнать, и это разные случаи.
            if kind in ('in', 'out'):
                if index % 3 == 0 and people:
                    values['peer_partner_id'] = people[index % len(people)].id
                else:
                    values['peer_address'] = '0x%040x' % (index * 65537 + 11)
            Tx.create(values)
        made['сеть %s/%s' % (kind, state)] = need
    return made


# ── Взаимный кредит ─────────────────────────────────────────────────────

def _credit_cases(env):
    Movement = env['coop.credit.movement'].sudo()
    Line = env['coop.credit.line'].sudo()
    lines = Line.search([], limit=60)
    if not lines:
        return {}
    rnd = _rnd()
    made = {}
    for state, title in (
        ('proposed', 'Помощь на площадке, смена'),
        ('declined', 'Не сошлись в оценке часов'),
        ('offset', 'Погашено взаимозачётом'),
    ):
        need = _need(env, 'coop.credit.movement', [('state', '=', state)])
        for index in range(need):
            line = lines[index % len(lines)]
            Movement.create({
                'line_id': line.id,
                'date': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'name': title,
                'amount': rnd.choice([-1, 1]) * rnd.randint(3, 30),
                'state': state,
                'proposed_by_id': line.partner_id.id,
                'confirmed_by_id': line.counterparty_id.id
                if state in ('offset',) else False,
            })
        made['кредит %s' % state] = need
    return made


def _clearing_cases(env):
    """Круги взаимозачёта во всех трёх состояниях.

    Подписанные и отменённые нужны не меньше предложенных: правило «не
    подписал один — раунд отменяется целиком» видно только на отменённом.
    """
    Clearing = env['coop.credit.clearing'].sudo()
    Signature = env['coop.credit.signature'].sudo()
    Line = env['coop.credit.line'].sudo()
    lines = Line.search([('balance', '!=', 0)], limit=200)
    if len(lines) < 9:
        return {}
    made = {}
    for state in ('proposed', 'signed', 'cancelled'):
        need = _need(env, 'coop.credit.clearing', [('state', '=', state)])
        for index in range(need):
            ring = lines[(index * 3) % (len(lines) - 3):][:3]
            if len(ring) < 3:
                continue
            participants = ring.mapped('partner_id') | ring.mapped('counterparty_id')
            clearing = Clearing.create({
                'name': 'Круг взаимных долгов № %s' % (index + 1),
                'amount': min(abs(line.balance) or 1 for line in ring),
                'participant_ids': [(6, 0, participants.ids)],
                'line_ids': [(6, 0, ring.ids)],
                'state': state,
            })
            for offset, partner in enumerate(participants):
                signed = state == 'signed' or (
                    state == 'proposed' and offset < len(participants) - 1)
                Signature.create({
                    'clearing_id': clearing.id,
                    'partner_id': partner.id,
                    'signed': signed,
                    'signed_on': fields.Date.context_today(clearing) if signed else False,
                })
        made['круг %s' % state] = need
    return made


# ── Паевой счёт ─────────────────────────────────────────────────────────

def _share_cases(env):
    Move = env['coop.share.move'].sudo()
    Account = env['coop.share.account'].sudo()
    accounts = Account.search([], limit=80)
    if not accounts:
        return {}
    rnd = _rnd()
    made = {}
    cases = [
        ('in_kind', 'confirmed', 'Взнос имуществом: трактор МТЗ-82',
         'Протокол общего собрания № 6', 'Отчёт об оценке № 114-О от 12.03.2025'),
        ('payout', 'confirmed', 'Выплата на руки по заявлению',
         'Заявление участника', False),
        ('return', 'confirmed', 'Возврат пая при выходе',
         'Протокол общего собрания № 9', False),
        ('payout', 'requested', 'Заявление на выплату', 'Заявление участника', False),
        ('payout', 'declined', 'Заявление отклонено: не истёк срок по уставу',
         'Решение правления № 3', False),
    ]
    for kind, state, title, basis, valuation in cases:
        need = _need(env, 'coop.share.move',
                     [('kind', '=', kind), ('state', '=', state)])
        for index in range(need):
            account = accounts[index % len(accounts)]
            amount = rnd.randint(20000, 180000)
            if kind in ('payout', 'return'):
                amount = -rnd.randint(3000, 60000)
            Move.create({
                'account_id': account.id,
                'date': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'name': title,
                'kind': kind,
                'basis': basis,
                'valuation_basis': valuation or False,
                'amount': amount,
                'state': state,
            })
        made['пай %s/%s' % (kind, state)] = need
    return made


# ── Сделки ──────────────────────────────────────────────────────────────

# ── Сделки: предметы, а не исходы ───────────────────────────────────────
#
# Прежде у каждого способа было одно название на все двадцать пять
# сделок, а у сделок, заведённых ради состояния, названием было само
# состояние: «Отменена по соглашению сторон», «Спор: недопоставка тары».
# Каталог из-за этого читался как журнал событий, а не как витрина, и
# картинку такой карточке подобрать было не из чего.
#
# Списки написаны под кооперативный обиход: техника, материалы, урожай,
# помещения, работа. Двадцать пять и больше на способ — чтобы при
# добавлении двадцати пяти записей не повторилось ни одно название.

PATHS = [
    ('rent', 'resource'),
    ('purchase', 'resource'),
    ('gift', 'resource'),
    ('exchange', 'resource'),
    ('job', 'work'),
    ('batch', 'resource'),
    ('credit', 'credit'),
    ('share', 'project'),
]

PRICE_PATHS = {
    'rent': (6000, 84000),
    'purchase': (12000, 190000),
    'gift': (0, 0),
    'exchange': (0, 0),
    'job': (18000, 120000),
    'batch': (35000, 340000),
    'credit': (15000, 260000),
    'share': (60000, 450000),
    'sale': (8000, 220000),
}

SUBJECT_PATHS = {
    'rent': [
        'Погрузчик вилочный на неделю',
        'Трактор МТЗ с прицепом на посевную',
        'Холодильная камера на время сбора',
        'Зерносушилка на месяц',
        'Бетономешалка на время заливки',
        'Строительные леса на фасадные работы',
        'Автолавка на выездную торговлю',
        'Грузовой фургон на переезд мастерской',
        'Швейный цех посменно',
        'Гончарная печь на обжиг партии',
        'Пилорама ленточная на сезон',
        'Сушильный шкаф для трав',
        'Мини-экскаватор на устройство дренажа',
        'Мотопомпа на откачку после паводка',
        'Сцена и звук на престольный праздник',
        'Фотостудия на съёмку каталога',
        'Коворкинг на время ремонта офиса',
        'Складской бокс на зиму',
        'Овощехранилище под картофель',
        'Автоклав для консервирования',
        'Медогонка на откачку',
        'Станок ЧПУ по дереву посменно',
        'Мойка высокого давления на неделю',
        'Палаточный городок на слёт кооперативов',
        'Прицеп-рефрижератор на развоз',
        'Генератор дизельный на время отключений',
    ],
    'purchase': [
        'Комплект досок обрезных, 40 кубов',
        'Утеплитель минеральный на ангар',
        'Саженцы яблони, двухлетки',
        'Семенной картофель, элита',
        'Пчелопакеты карпатской породы',
        'Профнастил на кровлю коровника',
        'Комбикорм на квартал',
        'Тара стеклянная под мёд',
        'Этикетка самоклеящаяся с печатью',
        'Мешки полипропиленовые под зерно',
        'Плёнка для теплиц армированная',
        'Кассеты рассадные',
        'Морозильный ларь для лавки',
        'Витрина холодильная в кооперативный магазин',
        'Кассовый аппарат с фискальным накопителем',
        'Ножи и фурнитура для столярного цеха',
        'Ткань льняная суровая, рулон',
        'Пряжа шерстяная на партию изделий',
        'Глазурь и глина для мастерской',
        'Сетка рабица на ограждение выпаса',
        'Трубы ПНД на летний водопровод',
        'Насос скважинный с автоматикой',
        'Солнечные панели на крышу сушилки',
        'Аккумуляторный инструмент, набор',
        'Весы товарные до 500 кг',
        'Стеллажи складские, секция',
    ],
    'gift': [
        'Комплект столярного инструмента мастерской',
        'Ноутбук для учебного класса кооператива',
        'Швейная машина начинающей мастерице',
        'Книги по агрономии в кооперативную библиотеку',
        'Рассада для школьной теплицы',
        'Мебель для общей комнаты',
        'Детские качели на общий двор',
        'Печь-буржуйка в сторожку',
        'Саженцы липы на медонос',
        'Ульи бывшие в употреблении',
        'Корм для приюта при кооперативе',
        'Проектор для собраний',
        'Аптечка и огнетушители в мастерскую',
        'Спортинвентарь в сельский клуб',
        'Музыкальные инструменты в ансамбль',
        'Инструмент для ремонта общей дороги',
        'Стройматериалы после разбора сарая',
        'Компьютер в правление кооператива',
        'Посуда для общей кухни',
        'Палатки для летнего лагеря',
        'Велосипеды для курьеров кооператива',
        'Ткани и фурнитура на благотворительный пошив',
        'Семена на общественный огород',
        'Сушилка для фруктов в школьную столовую',
        'Скамейки на остановку',
        'Светильники на общий проезд',
    ],
    'exchange': [
        'Мёд на пиломатериал',
        'Картофель на комбикорм',
        'Сыр на сено',
        'Пиломатериал на кровельные работы',
        'Саженцы на вспашку участка',
        'Шерсть на пряжу',
        'Зерно на муку с мельницы',
        'Молоко на закваски и упаковку',
        'Керамика на обжиг чужой партии',
        'Дрова на ремонт трактора',
        'Овощи на хранение в чужом погребе',
        'Мясо на забой и разделку',
        'Ягода на переработку в морс',
        'Лён на ткачество',
        'Рыба на копчение',
        'Доски на столярные изделия',
        'Яйцо на инкубацию',
        'Навоз на доставку и разбрасывание',
        'Металлолом на сварочные работы',
        'Соломенные блоки на монтаж стен',
        'Кирпич на кладку печи',
        'Хмель на варку сидра',
        'Травы на сушку и фасовку',
        'Место на складе на место в холодильнике',
        'Часы работы на кухне на часы работы в поле',
        'Печать этикеток на дизайн упаковки',
    ],
    'job': [
        'Оператор сушилки на сезон',
        'Тракторист на посевную',
        'Пекарь в кооперативную пекарню',
        'Сыровар на малое производство',
        'Швея на партию изделий',
        'Столяр-краснодеревщик',
        'Сварщик на монтаж ангара',
        'Электрик на подключение цеха',
        'Водитель развозного фургона',
        'Кладовщик на сезон хранения',
        'Бухгалтер на четверть ставки',
        'Агроном-консультант на выезд',
        'Ветеринар на обслуживание фермы',
        'Пасечник на медосбор',
        'Продавец в кооперативную лавку',
        'Маркетолог на запуск витрины',
        'Фотограф на съёмку каталога',
        'Разработчик на доработку учёта',
        'Оператор ЧПУ на смену',
        'Мастер по ремонту техники',
        'Повар на полевую кухню',
        'Разнорабочий на уборку урожая',
        'Кровельщик на перекрытие склада',
        'Печник на кладку хлебной печи',
        'Переводчик на переговоры с поставщиком',
        'Юрист на сопровождение регистрации',
    ],
    'batch': [
        'Картофель, 3 тонны',
        'Морковь столовая, 2 тонны',
        'Капуста белокочанная, 4 тонны',
        'Зерно фуражное, 10 тонн',
        'Мёд разнотравье, 800 кг',
        'Сыр полутвёрдый, 300 кг',
        'Яблоки зимних сортов, 5 тонн',
        'Лук репчатый, 2,5 тонны',
        'Свёкла столовая, 3 тонны',
        'Тыква продовольственная, 1,5 тонны',
        'Огурец тепличный, 900 кг',
        'Томат грунтовой, 1,2 тонны',
        'Ягода замороженная, 600 кг',
        'Рыба охлаждённая, 400 кг',
        'Мясо птицы, 700 кг',
        'Яйцо столовое, 20 тысяч штук',
        'Молоко сырое, 6 тонн',
        'Сено в рулонах, 40 рулонов',
        'Дрова колотые, 60 кубов',
        'Пиломатериал обрезной, 25 кубов',
        'Пеллеты топливные, 8 тонн',
        'Мука пшеничная, 3 тонны',
        'Крупа гречневая, 1,5 тонны',
        'Масло подсолнечное нерафинированное, 900 литров',
        'Варенье в банках, 4 тысячи единиц',
        'Саженцы плодовых, 2 тысячи штук',
    ],
    'credit': [
        'Отсрочка по поставке комбикорма',
        'Отсрочка по партии тары',
        'Рассрочка на зерносушилку',
        'Рассрочка на холодильное оборудование',
        'Отсрочка по семенному материалу',
        'Товарный кредит на удобрения',
        'Товарный кредит на топливо к посевной',
        'Отсрочка по аренде склада',
        'Рассрочка на кассовое оборудование',
        'Отсрочка по кровельным материалам',
        'Товарный кредит на пчелопакеты',
        'Рассрочка на швейное оборудование',
        'Отсрочка по услугам ветеринара',
        'Рассрочка на автолавку',
        'Отсрочка по типографским услугам',
        'Товарный кредит на упаковку',
        'Рассрочка на станок ЧПУ',
        'Отсрочка по транспортным услугам',
        'Товарный кредит на саженцы',
        'Рассрочка на солнечные панели',
        'Отсрочка по ремонту трактора',
        'Товарный кредит на стройматериалы',
        'Рассрочка на весовое оборудование',
        'Отсрочка по услугам бухгалтера',
        'Товарный кредит на корма к зимовке',
        'Рассрочка на мельничный комплекс',
    ],
    'share': [
        'Вклад техникой в сыроварню',
        'Вклад трудом в пекарню',
        'Вклад помещением под мастерскую',
        'Вклад деньгами в тепличный комплекс',
        'Вклад землёй в питомник саженцев',
        'Вклад оборудованием в столярный цех',
        'Вклад транспортом в развозку',
        'Вклад проектной работой в ферму',
        'Вклад пчелосемьями в пасеку',
        'Вклад стройматериалами в ангар',
        'Вклад программой учёта в кооператив',
        'Вклад станком в металлообработку',
        'Вклад складом в распределительный центр',
        'Вклад печью в керамическую мастерскую',
        'Вклад дизайном в витрину кооператива',
        'Вклад автолавкой в выездную торговлю',
        'Вклад холодильником в хранение ягоды',
        'Вклад сушилкой в переработку трав',
        'Вклад мельницей в помольный участок',
        'Вклад семенным фондом в севооборот',
        'Вклад стадом в молочную ферму',
        'Вклад лесом на корню в пилораму',
        'Вклад солнечной станцией в энергоснабжение',
        'Вклад обучением в кооперативную школу',
        'Вклад правовым сопровождением в союз',
        'Вклад лабораторией в контроль качества',
    ],
}

# Сделки, заведённые ради состояния, торгуют тем же, чем и остальные:
# состояние — это поле, а не предмет. «Отменена» и «в споре» ничем не
# должны выделяться в каталоге, кроме значка состояния.
#
# Пул длиннее сотни намеренно: состояний четыре, на каждое по двадцать
# пять сделок, и каждое состояние берёт свой кусок списка (см. сдвиг в
# `_предмет`). На пуле короче ста «Отменена» и «На приёмке» вышли бы под
# одним названием — та же беда, что чинится, только с другой стороны.
SALE = [
    'Дизельное топливо, бочка 200 литров',
    'Запасные части к трактору',
    'Шины на грузовой прицеп',
    'Бочки пищевые под засолку',
    'Ящики деревянные под ягоду',
    'Поддоны европейские, партия',
    'Стретч-плёнка для паллет',
    'Сепаратор молочный',
    'Маслопресс шнековый',
    'Дровокол гидравлический',
    'Мотоблок с навесным оборудованием',
    'Опрыскиватель садовый',
    'Инкубатор на 500 яиц',
    'Доильный аппарат',
    'Косилка роторная',
    'Грабли-ворошилка',
    'Сушильные сетки для трав',
    'Термоусадочное оборудование для банок',
    'Печь хлебная подовая',
    'Тестомес спиральный',
    'Мельница вальцовая',
    'Коптильня горячего копчения',
    'Оборудование для розлива мёда',
    'Пресс для сыра',
    'Линия фасовки круп',
    'Автолавка на базе фургона',
    'Сноповязалка к мини-трактору',
    'Картофелекопалка навесная',
    'Сеялка точного высева',
    'Плуг оборотный двухкорпусный',
    'Борона дисковая',
    'Культиватор междурядный',
    'Разбрасыватель органики',
    'Прицеп самосвальный тракторный',
    'Погрузчик фронтальный навесной',
    'Ковш для сыпучих грузов',
    'Бак для воды на 5 кубов',
    'Система капельного полива на гектар',
    'Метеостанция для поля',
    'Ульи-лежаки, комплект на пасеку',
    'Воскотопка паровая',
    'Рамки и вощина на сезон',
    'Стол для распечатки сот',
    'Клетки для перепелов, батарея',
    'Брудер для цыплят',
    'Кормораздатчик для коровника',
    'Поилки автоматические, комплект',
    'Станок для обрезки копыт',
    'Весы для взвешивания скота',
    'Морозильная камера шоковой заморозки',
    'Вакуумный упаковщик',
    'Термопринтер для маркировки',
    'Сканер штрихкодов для лавки',
    'Терминал сбора данных',
    'Стеллаж торговый пристенный',
    'Прилавок охлаждаемый',
    'Кофемашина для кооперативной лавки',
    'Тепловая завеса на вход магазина',
    'Кассовый узел под ключ',
    'Вывеска с подсветкой',
    'Станок токарный по металлу',
    'Сварочный полуавтомат',
    'Компрессор поршневой с ресивером',
    'Гильотина листовая ручная',
    'Трубогиб профильный',
    'Верстак слесарный с тисками',
    'Шлифовальный станок по дереву',
    'Фрезер ручной с набором фрез',
    'Сушильная камера для пиломатериала',
    'Ленточнопильный станок',
    'Гончарный круг с подставкой',
    'Муфельная печь для керамики',
    'Ткацкий станок напольный',
    'Прялка электрическая',
    'Раскройный стол для швейного цеха',
    'Оверлок промышленный',
    'Вышивальная машина одноголовочная',
    'Термопресс для нанесения на ткань',
    'Станок для печати на упаковке',
    'Резак для картона',
    'Стеллажи паллетные, ряд',
    'Рохля гидравлическая',
    'Штабелёр ручной',
    'Ворота секционные на склад',
    'Рампа перегрузочная',
    'Система видеонаблюдения склада',
    'Пожарная сигнализация в цех',
    'Котёл твердотопливный на цех',
    'Тепловой насос для теплицы',
    'Ветрогенератор малой мощности',
    'Инвертор с аккумуляторами',
    'Насосная станция на водозабор',
    'Фильтры водоподготовки для сыроварни',
    'Лаборатория контроля молока',
    'Аппарат для розлива в бутылку',
    'Этикетировочная машина',
    'Установка обратного осмоса',
    'Дробилка кормов',
    'Гранулятор для пеллет',
    'Рубительная машина для щепы',
    'Электростанция резервная на ферму',
    'Прицеп-цистерна для воды',
    'Фургон изотермический подержанный',
    'Микроавтобус для развоза бригад',
]

SUBJECT_PATHS['sale'] = SALE

# Сдвиг по списку продаж: своё окно на каждое состояние. Окна не
# пересекаются и не пересекаются со списками способов — иначе одна и та
# же «Косилка роторная» досталась бы и спорной сделке, и отменённой, и
# каталог снова читался бы как один текст с разными значками.
STATE_SHIFT = {
    'draft': 0,
    'acceptance': 26,
    'disputed': 52,
    'cancelled': 78,
}

# Что стояло в названии до починки. По этому списку опознаются записи,
# которые надо переименовать; всё остальное — правка человека, её не
# трогаем.
OLD_TITLES = {
    'Аренда: погрузчик на неделю',
    'Покупка: комплект досок обрезных',
    'Передача в дар: комплект инструмента',
    'Обмен: мёд на пиломатериал',
    'Работа по вакансии: оператор сушилки',
    'Продажа партией: картофель, 3 тонны',
    'Взаимный кредит: отсрочка по поставке',
    'Вклад в проект в обмен на долю',
    'Переговоры: аренда ангара под хранение',
    'На приёмке: партия саженцев',
    'Спор: недопоставка тары',
    'Отменена по соглашению сторон',
}

DEAL_CITIES = [
    'Москва', 'Пермь', 'Казань', 'Омск', 'Тюмень', 'Воронеж',
    'Ростов-на-Дону', 'Новосибирск', 'Екатеринбург', 'Уфа', 'Самара',
    'Челябинск', 'Ярославль', 'Владивосток', 'Краснодар', 'Вологда',
    'Архангельск', 'Красноярск', 'Волгоград', 'Хабаровск',
]


def _deal_cases(env):
    """Способы и состояния сделок, которых мало или нет вовсе.

    Дар и обмен важны отдельно: на них не бывает суммы, и именно они
    ломались бы, будь сделка сделана заказом Odoo.
    """
    Deal = env['coop.deal'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=60)
    companies = Partner.search([('coop_is_participant', '=', True),
                                ('is_company', '=', True)], limit=40)
    if len(people) < 2 or not companies:
        return {}
    rnd = _rnd()
    made = {}

    for way, subject in PATHS:
        need = _need(env, 'coop.deal', [('way', '=', way)])
        for index in range(need):
            first = people[index % len(people)]
            second = companies[index % len(companies)]
            title, amount = _subject(way, index, rnd)
            Deal.create({
                'name': title,
                'subject': subject,
                'way': way,
                'party_a_id': first.id,
                'party_b_id': second.id,
                'role_a': 'сторона',
                'role_b': 'вторая сторона',
                'city': DEAL_CITIES[index % len(DEAL_CITIES)],
                'amount': amount,
                'signed_on': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'state': 'active',
                'import_key': 'examples.way.%s.%s' % (way, index),
            })
        made['сделка %s' % way] = need

    for state in ('draft', 'acceptance', 'disputed', 'cancelled'):
        need = _need(env, 'coop.deal', [('state', '=', state)])
        for index in range(need):
            first = people[(index + 7) % len(people)]
            second = companies[(index + 3) % len(companies)]
            title, amount = _subject(
                'sale', index + STATE_SHIFT[state], rnd)
            values = {
                'name': title,
                'subject': 'resource',
                'way': 'sale',
                'party_a_id': first.id,
                'party_b_id': second.id,
                'role_a': 'продавец',
                'role_b': 'покупатель',
                'city': DEAL_CITIES[(index + 5) % len(DEAL_CITIES)],
                'amount': amount,
                'signed_on': '2026-%02d-%02d' % (1 + index % 9, 1 + index % 27),
                'state': state,
                'import_key': 'examples.state.%s.%s' % (state, index),
            }
            if state == 'acceptance':
                # Одна сторона акт подтвердила, вторая ещё нет — ровно то,
                # что в макете названо «ждёт вас» и «ждёт контрагента».
                values['act_confirmed_a'] = index % 2 == 0
                values['act_confirmed_b'] = index % 2 == 1
            if state == 'disputed':
                values['dispute_opened_by_id'] = first.id
                values['dispute_reason'] = (
                    'Поставлено меньше согласованного, тара не соответствует '
                    'спецификации.')
            Deal.create(values)
        made['сделка %s' % state] = need

    made.update(_rename_deals(env, rnd))
    return made


def _rename_deals(env, rnd):
    """Починить названия у сделок, заведённых прежней версией загрузчика.

    Загрузчик добирает, а не пересоздаёт, — значит новые названия сами
    собой до уже заведённых записей не доедут: `_need` видит, что сделок
    хватает, и не делает ничего. Поэтому отдельный проход по своим же
    записям, опознанным по `import_key`.

    Трогаются только те, у которых название совпало со старой заготовкой.
    Переименовал человек — имя остаётся: его правка дороже нашей ровности.
    """
    Deal = env['coop.deal'].sudo()
    records = Deal.search([('import_key', '=like', 'examples.%')])
    fixed_count = 0
    for deal in records:
        if deal.name not in OLD_TITLES:
            continue
        key = deal.import_key or ''
        try:
            index = int(key.rsplit('.', 1)[-1])
        except ValueError:
            index = 0
        if key.startswith('examples.state.'):
            # examples.state.<состояние>.<номер> — сдвиг берётся из ключа,
            # а не из поля состояния: состояние сделки участник меняет
            # своими действиями, и после согласования спорная сделка
            # перестала бы опознаваться собственным окном списка.
            state = key.split('.')[2] if len(key.split('.')) > 3 else ''
            way = 'sale'
            index += STATE_SHIFT.get(state, 0)
        else:
            way = deal.way if deal.way in SUBJECT_PATHS else 'sale'
        title, amount = _subject(way, index, rnd)
        values = {'name': title}
        # Сумма переписывается только там, где она была одинаковой у всех
        # двадцати пяти: у сделок по состоянию разброс был и раньше, и
        # менять его — значит терять уже показанное.
        if key.startswith('examples.way.'):
            values['amount'] = amount
        if not deal.city:
            values['city'] = DEAL_CITIES[index % len(DEAL_CITIES)]
        deal.write(values)
        fixed_count += 1
    return {'сделка переименована': fixed_count} if fixed_count else {}


def _subject(way, index, rnd):
    """Название предмета сделки и сумма под него.

    Название — предмет, а не исход. «Отменена по соглашению сторон» —
    это состояние: оно стоит в поле состояния и значком в подвале
    карточки, а в названии занимает место того, о чём сделка была. С ним
    каталог читается как журнал, и картинку такой карточке не подобрать —
    искать нечего.
    """
    subjects = SUBJECT_PATHS.get(way) or SUBJECT_PATHS['sale']
    title = subjects[index % len(subjects)]
    bottom, top = PRICE_PATHS.get(way, (8000, 220000))
    if top == 0:
        return title, 0
    # Шаг в пятьсот рублей: суммы в объявлениях круглые, и случайное
    # число до рубля выдаёт машинное происхождение с первого взгляда.
    return title, rnd.randrange(bottom, top + 1, 500)


def _payment_cases(env):
    Payment = env['coop.deal.payment'].sudo()
    Deal = env['coop.deal'].sudo()
    deals = Deal.search([('amount', '>', 0)], limit=80)
    if not deals:
        return {}
    rnd = _rnd()
    made = {}
    for state, title in (
        ('overdue', 'Просроченный платёж'),
        ('cancelled', 'Платёж отменён при пересмотре условий'),
    ):
        need = _need(env, 'coop.deal.payment', [('state', '=', state)])
        for index in range(need):
            deal = deals[index % len(deals)]
            Payment.create({
                'deal_id': deal.id,
                'name': title,
                'due_on': '2026-%02d-%02d' % (1 + index % 8, 1 + index % 27),
                'amount': rnd.randint(4000, 60000),
                'state': state,
            })
        made['платёж %s' % state] = need
    return made


def _review_cases(env):
    """Оценки, которых нет: тройки, четвёрки и единицы.

    Без них доверие считается по двум крайностям, и середины — «сделали,
    но со скрипом» — в данных не существует, хотя в жизни она частая.
    """
    Review = env['coop.deal.review'].sudo()
    Deal = env['coop.deal'].sudo()
    made = {}
    texts = {
        '1': 'Договорённости не выполнены, пришлось искать замену.',
        '2': 'Сроки сорваны, качество ниже согласованного.',
        '3': 'Сделали, но со скрипом: сроки плыли, качество среднее.',
        '4': 'В целом хорошо, мелкие замечания по срокам.',
    }
    for rating, body in texts.items():
        need = _need(env, 'coop.deal.review', [('rating', '=', rating)])
        if not need:
            made['отзыв %s' % rating] = 0
            continue
        # Отзыв можно оставить только по завершённой сделке и только
        # один от каждой стороны. Сначала берём те, где своего отзыва ещё
        # нет; если их не хватает — заводим завершённые сделки под
        # оценку. Второе не подтасовка: сделка с одной средней оценкой —
        # обычное дело, а без неё середина шкалы в данных не существует.
        deals = Deal.search([('state', '=', 'done')], limit=600)
        created = 0
        for deal in deals:
            if created >= need:
                break
            authors = set(deal.review_ids.mapped('author_id').ids)
            for author, target in ((deal.party_a_id, deal.party_b_id),
                                   (deal.party_b_id, deal.party_a_id)):
                if created >= need or author.id in authors:
                    continue
                Review.create({
                    'deal_id': deal.id,
                    'author_id': author.id,
                    'target_id': target.id,
                    'rating': rating,
                    'body': body,
                })
                authors.add(author.id)
                created += 1
        created += _reviews_on_new_deals(env, rating, body, need - created)
        made['отзыв %s' % rating] = created
    return made


def _reviews_on_new_deals(env, rating, body, need):
    """Завести завершённые сделки под недостающие оценки."""
    if need <= 0:
        return 0
    Deal = env['coop.deal'].sudo()
    Review = env['coop.deal.review'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=80)
    companies = Partner.search([('coop_is_participant', '=', True),
                                ('is_company', '=', True)], limit=40)
    if len(people) < 2 or not companies:
        return 0
    created = 0
    for index in range(need):
        first = people[(index * 11 + int(rating)) % len(people)]
        second = companies[(index * 5 + int(rating)) % len(companies)]
        deal = Deal.create({
            'name': 'Поставка по договорённости',
            'subject': 'resource',
            'way': 'sale',
            'party_a_id': first.id,
            'party_b_id': second.id,
            'role_a': 'продавец',
            'role_b': 'покупатель',
            'amount': 15000 + index * 1300,
            'signed_on': '2026-0%s-%02d' % (1 + index % 8, 1 + index % 27),
            'state': 'done',
            'act_confirmed_a': True,
            'act_confirmed_b': True,
            'import_key': 'examples.review.%s.%s' % (rating, index),
        })
        Review.create({
            'deal_id': deal.id,
            'author_id': first.id,
            'target_id': second.id,
            'rating': rating,
            'body': body,
        })
        created += 1
    return created


# ── Токены ──────────────────────────────────────────────────────────────

def _token_cases(env):
    Token = env['coop.token.transaction'].sudo()
    Partner = env['res.partner'].sudo()
    partners = Partner.search([('coop_is_participant', '=', True)], limit=60)
    if not partners:
        return {}
    rnd = _rnd()
    made = {}
    for kind, sign, title in (
        ('grant', 1, 'Начисление за вклад в общее дело'),
        ('refund', 1, 'Возврат за неиспользованное продвижение'),
        ('correction', -1, 'Корректировка по обращению участника'),
        ('promotion', -1, 'Оплата продвижения объявления'),
    ):
        need = _need(env, 'coop.token.transaction', [('kind', '=', kind)])
        for index in range(need):
            Token.create({
                'partner_id': partners[index % len(partners)].id,
                'amount': sign * rnd.randint(5, 240),
                'kind': kind,
                'description': title,
            })
        made['токены %s' % kind] = need
    return made


# ── Верификация ─────────────────────────────────────────────────────────

def _verification_cases(env):
    """Заявки на проверку в состояниях, которых не было.

    Ожидающая и отклонённая проверка — рабочие состояния: человек подал,
    правление ещё не сверило либо документ не подошёл. Экрана для них не
    было на чём проверить.
    """
    Verification = env['coop.verification'].sudo()
    Partner = env['res.partner'].sudo()
    made = {}
    cases = [
        ('identity', 'pending', 'inperson'),
        ('identity', 'rejected', 'inperson'),
        ('phone', 'pending', 'self'),
        ('email', 'pending', 'self'),
        ('registry', 'pending', 'registry'),
    ]
    for kind, state, method in cases:
        need = _need(env, 'coop.verification',
                     [('kind', '=', kind), ('state', '=', state)])
        if not need:
            made['проверка %s/%s' % (kind, state)] = 0
            continue
        is_company = kind == 'registry'
        pool = Partner.search([
            ('coop_is_participant', '=', True),
            ('is_company', '=', is_company),
        ], order='id desc', limit=300)
        created = 0
        for partner in pool:
            if created >= need:
                break
            if Verification.search_count([('partner_id', '=', partner.id),
                                          ('kind', '=', kind)]):
                continue
            Verification.create({
                'partner_id': partner.id,
                'kind': kind,
                'method': method,
                'state': state,
                'note': 'Документ не соответствует заявленному'
                if state == 'rejected' else False,
            })
            created += 1
        created += _newcomers_for_verification(
            env, kind, state, method, need - created)
        made['проверка %s/%s' % (kind, state)] = created
    return made


def _newcomers_for_verification(env, kind, state, method, need):
    """Завести новичков, ждущих проверки.

    Свободных участников без такой проверки может не остаться: почти все
    в демо-данных уже подтверждены. Но платформа всегда имеет поток
    новых регистраций, ждущих проверки, — и это не выдумка ради цифры, а
    состояние, которое на работающем узле есть всегда.

    Новички попадают и в каталог людей — неподтверждёнными, как и
    положено: ступень «не подтверждён» тоже надо на чём-то показывать.
    """
    if need <= 0:
        return 0
    if kind == 'registry':
        return _newcomer_orgs(env, state, method, need)
    Partner = env['res.partner'].sudo()
    Verification = env['coop.verification'].sudo()
    # Отчество подбирается по случаю, чтобы у разных состояний были
    # разные люди: иначе второй случай упрётся в тех же, у кого проверка
    # уже заведена.
    # Отчество в двух видах сразу. Раньше бралось одно мужское на всех,
    # и в каталоге людей стояли «Белкина Ольга Викторович» и «Жукова
    # Инна Сергеевич» — четырнадцать таких. Ошибки нет, запись
    # создаётся, и видно это только глазами в каталоге.
    base = {
        ('identity', 'pending'): ('Сергеевич', 'Сергеевна'),
        ('identity', 'rejected'): ('Викторович', 'Викторовна'),
        ('phone', 'pending'): ('Данилович', 'Даниловна'),
        ('email', 'pending'): ('Максимович', 'Максимовна'),
    }.get((kind, state), ('Иванович', 'Ивановна'))
    names = [
        'Астахов Роман', 'Белкина Ольга', 'Гущин Артём', 'Дорохова Вера',
        'Ерёмин Павел', 'Жукова Инна', 'Зимин Кирилл', 'Ильина Раиса',
        'Кабанов Тимур', 'Лапина Дарья', 'Мещеряков Игорь', 'Нечаева Юлия',
        'Осипов Глеб', 'Панина Алла', 'Рогов Матвей', 'Седова Ксения',
        'Тарасов Лев', 'Ушакова Нина', 'Фомин Аркадий', 'Хохлова Елена',
        'Цветков Борис', 'Чернова Анна', 'Шилов Егор', 'Щукина Софья',
        'Юрьев Данила', 'Яшина Полина',
    ]
    cities = ['Пермь', 'Омск', 'Тула', 'Казань', 'Ижевск', 'Курск', 'Псков']
    created = 0
    for index in range(need):
        full_name = names[index % len(names)]
        # Пол определяется по фамилии: русская женская фамилия кончается
        # на «-ова», «-ева», «-ина», «-ская». Способ не универсальный —
        # «Черных» и «Шевченко» он не различит, — но в этом списке
        # фамилии обычные, и здесь его хватает.
        female = full_name.split()[0].endswith(('ова', 'ева', 'ёва', 'ина',
                                           'ская', 'ая'))
        name = '%s %s' % (full_name, base[1] if female else base[0])
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'is_company': False,
                'coop_is_participant': True,
                'city': cities[index % len(cities)],
            })
        if Verification.search_count([('partner_id', '=', partner.id),
                                      ('kind', '=', kind)]):
            continue
        Verification.create({
            'partner_id': partner.id,
            'kind': kind,
            'method': method,
            'state': state,
            'note': 'Документ не соответствует заявленному'
            if state == 'rejected' else False,
        })
        created += 1
    return created


def _newcomer_orgs(env, state, method, need):
    """Организации, только что подавшие сведения на сверку с реестром."""
    Partner = env['res.partner'].sudo()
    Verification = env['coop.verification'].sudo()
    forms = ['ООО', 'ПК', 'СПК', 'ТСЖ', 'АНО', 'Фонд', 'Артель']
    words = [
        'Заречье', 'Родник', 'Пойма', 'Веретено', 'Пасека', 'Оберег',
        'Слобода', 'Подворье', 'Заимка', 'Житница', 'Мельница', 'Криница',
        'Дубрава', 'Затон', 'Ольховка', 'Березань', 'Гончар', 'Скобянка',
        'Полесье', 'Взгорье', 'Тропа', 'Пристань', 'Кузня', 'Сенник',
        'Овражки', 'Луговина',
    ]
    created = 0
    for index in range(need):
        name = '%s «%s»' % (forms[index % len(forms)], words[index % len(words)])
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': name,
                'is_company': True,
                'coop_is_participant': True,
            })
        if Verification.search_count([('partner_id', '=', partner.id),
                                      ('kind', '=', 'registry')]):
            continue
        Verification.create({
            'partner_id': partner.id,
            'kind': 'registry',
            'method': method,
            'state': state,
        })
        created += 1
    return created


# ── Отклики и заявки ────────────────────────────────────────────────────

def _application_cases(env):
    VacancyApp = env['coop.vacancy.application'].sudo()
    Vacancy = env['coop.vacancy'].sudo()
    BountyApp = env['coop.bounty.application'].sudo()
    Task = env['coop.bounty.task'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=200)
    made = {}

    vacancies = Vacancy.search([('state', '=', 'published')], limit=200)
    for state, letter in (
        ('applied', 'Работал на похожем оборудовании три сезона.'),
        ('invited', 'Приглашаем на разговор, свяжемся на неделе.'),
        ('declined', 'В этот раз выбрали другого кандидата.'),
    ):
        need = _need(env, 'coop.vacancy.application', [('state', '=', state)])
        created = 0
        for index, vacancy in enumerate(vacancies):
            if created >= need:
                break
            person = people[(index * 5 + hash(state) % 7) % len(people)]
            if VacancyApp.search_count([('vacancy_id', '=', vacancy.id),
                                        ('partner_id', '=', person.id)]):
                continue
            try:
                with env.cr.savepoint():
                    VacancyApp.create({
                        'vacancy_id': vacancy.id,
                        'partner_id': person.id,
                        'message': letter,
                        'state': state,
                    })
                created += 1
            except Exception:  # noqa: BLE001
                continue
        made['отклик %s' % state] = created

    tasks = Task.search([], limit=200)
    for state in ('applied', 'approved', 'rejected'):
        need = _need(env, 'coop.bounty.application', [('state', '=', state)])
        created = 0
        pairs = [(task, offset) for task in tasks for offset in range(10)]
        for index, (task, offset) in enumerate(pairs):
            if created >= need:
                break
            person = people[(index * 3 + offset * 11 + len(state)) % len(people)]
            if BountyApp.search_count([('task_id', '=', task.id),
                                       ('partner_id', '=', person.id)]):
                continue
            try:
                with env.cr.savepoint():
                    BountyApp.create({
                        'task_id': task.id,
                        'partner_id': person.id,
                        'state': state,
                    })
                created += 1
            except Exception:  # noqa: BLE001
                continue
        made['заявка %s' % state] = created
    return made


def _friendship_cases(env):
    Friendship = env['coop.friendship'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=200)
    if len(people) < 10:
        return {}
    made = {}
    # Отсчёт пар сквозной, а не с нуля на каждое состояние. С нуля каждое
    # состояние бралось за те же самые пары, и одна пара заводилась трижды
    # — на стенде так вышло 25 пар-дублей из 75 связей. Уникальности в
    # базе тогда не было (см. `models.Constraint`), и дубли просто копили
    # счётчик друзей: у человека с одним другом их выходило три.
    index = 0
    for state in ('pending', 'accepted', 'declined'):
        need = _need(env, 'coop.friendship', [('state', '=', state)])
        created = 0
        attempts = 0
        while created < need and attempts < len(people) * 3:
            first = people[index % len(people)]
            second = people[(index * 7 + 13) % len(people)]
            index += 1
            attempts += 1
            if first == second:
                continue
            try:
                with env.cr.savepoint():
                    Friendship.create({
                        'requester_id': first.id,
                        'addressee_id': second.id,
                        'state': state,
                    })
                created += 1
            except Exception:  # noqa: BLE001
                continue
        made['дружба %s' % state] = created
    return made


def _contribution_cases(env):
    Contribution = env['coop.project.contribution'].sudo()
    Project = env['coop.project'].sudo()
    Partner = env['res.partner'].sudo()
    projects = Project.search([('state', '=', 'gathering')], limit=80)
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=60)
    if not projects or not people:
        return {}
    rnd = _rnd()
    made = {}
    for state, title in (
        ('offered', 'Предложен: ждёт оценки инициатора'),
        ('declined', 'Отклонён: оценка вклада не согласована'),
        ('returned', 'Возвращён по выходу участника из проекта'),
    ):
        need = _need(env, 'coop.project.contribution', [('state', '=', state)])
        for index in range(need):
            project = projects[index % len(projects)]
            Contribution.create({
                'project_id': project.id,
                'partner_id': people[index % len(people)].id,
                'kind': rnd.choice(['money', 'labour', 'resource', 'material']),
                'name': title,
                'value': rnd.randint(15000, 300000),
                'state': state,
            })
        made['вклад %s' % state] = need
    return made


def _project_state_cases(env):
    """Проекты во всех состояниях пути.

    Запущенных и завершённых в макете почти нет: там готовность нигде не
    доходит до ста. А именно на них проверяется передача проекта в модуль
    управления и распределение долей по итогам — то, ради чего
    краудресурсинг и затевается.
    """
    Project = env['coop.project'].sudo()
    Contribution = env['coop.project.contribution'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=60)
    if not people:
        return {}
    made = {}
    # Идеи в этом списке нет намеренно. Добор переводил в черновики
    # проекты, которые уже собрали деньги, — и в каталоге оказалось
    # полсотни «идей» с вкладами. Идея — это то, что ещё не
    # начинали собирать; такие заводит сам каталог проектов, и их
    # достаточно, чтобы состояние было на чём проверить.
    for state in ('running', 'done', 'cancelled'):
        need = _need(env, 'coop.project', [('state', '=', state)])
        created = 0
        # Проще довести до состояния уже собранные проекты, чем заводить
        # новые: у них есть вклады, а без вкладов «запущенный» проект —
        # запись ни о чём.
        # Порядок разный по смыслу. Запускают и завершают тех, кто почти
        # собрался, — их дособрать дешевле и правдоподобнее. Отменяют
        # наоборот, тех, кто не тронулся: проект на девяноста пяти
        # процентах закрывают в последнюю очередь.
        #
        # Пока порядок был один на все случаи, под отмену попадали самые
        # собранные — а после того, как в каталог пришли ДАО-проекты с
        # высокой готовностью, отменёнными оказались девять из двадцати.
        order = 'readiness asc' if state == 'cancelled' else 'readiness desc'
        pool = Project.search([('state', '=', 'gathering')], order=order)
        for project in pool:
            if created >= need:
                break
            if state in ('running', 'done') and project.readiness < 100:
                # Дособрать вкладом: запускать недособранный проект
                # нельзя, и обходить собственное правило в данных тоже.
                missing = project.required_total - project.contribution_total
                if missing > 0:
                    Contribution.create({
                        'project_id': project.id,
                        'partner_id': people[created % len(people)].id,
                        'kind': 'money',
                        'name': 'Замыкающий взнос',
                        'value': missing,
                        'state': 'accepted',
                    })
            project.state = state
            # Проект в модуле управления здесь не заводится. Он создаётся
            # кнопкой запуска, и при загрузке модулей это не проходит:
            # у штатного проекта есть обязательное поле, которое
            # добавляет модуль учёта времени, и его значение при загрузке
            # до записи не доезжает. Ради демонстрационных данных
            # обходить чужую механику незачем — состояния «запущен» и
            # «завершён» показывают то, ради чего они нужны, и без этой
            # ссылки.
            created += 1
        made['проект %s' % state] = created
    return made


def _outcome_cases(env):
    """Итоги сделок: недовольные обе стороны и ждущие второго отзыва.

    Итог считается из отзывов, поэтому его нельзя проставить — только
    сложить из оценок. «Ждём отзывов» получается там, где написал один;
    «обе недовольны» — где оба поставили низкую оценку. Оба состояния в
    жизни частые, и без них экран сделок показывает только успех.
    """
    Deal = env['coop.deal'].sudo()
    Review = env['coop.deal.review'].sudo()
    Partner = env['res.partner'].sudo()
    people = Partner.search([('coop_is_participant', '=', True),
                             ('is_company', '=', False)], limit=80)
    companies = Partner.search([('coop_is_participant', '=', True),
                                ('is_company', '=', True)], limit=40)
    if len(people) < 2 or not companies:
        return {}
    made = {}
    for outcome, both, rating, body in (
        ('negative', True, '2', 'Договорённости не выдержаны обеими сторонами.'),
        ('pending', False, '4', 'Свою оценку поставил, жду ответной.'),
    ):
        need = _need(env, 'coop.deal', [('outcome', '=', outcome)])
        for index in range(need):
            first = people[(index * 13 + len(outcome)) % len(people)]
            second = companies[(index * 7 + len(outcome)) % len(companies)]
            deal = Deal.create({
                'name': 'Поставка по договорённости',
                'subject': 'resource',
                'way': 'sale',
                'party_a_id': first.id,
                'party_b_id': second.id,
                'role_a': 'продавец',
                'role_b': 'покупатель',
                'amount': 12000 + index * 900,
                'signed_on': '2026-%02d-%02d' % (1 + index % 8, 1 + index % 27),
                'state': 'done',
                'act_confirmed_a': True,
                'act_confirmed_b': True,
                'import_key': 'examples.outcome.%s.%s' % (outcome, index),
            })
            Review.create({
                'deal_id': deal.id, 'author_id': first.id,
                'target_id': second.id, 'rating': rating, 'body': body,
            })
            if both:
                Review.create({
                    'deal_id': deal.id, 'author_id': second.id,
                    'target_id': first.id, 'rating': rating, 'body': body,
                })
        made['итог %s' % outcome] = need
    return made

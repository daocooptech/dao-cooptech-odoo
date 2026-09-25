# -*- coding: utf-8 -*-
"""Внешнеторговые контракты (решения 392, 410).

Каталог наполняется не менее чем сотней-двумя примеров. Здесь сто
тридцать контрактов с пятнадцатью странами, и раскладка неровная, как в
жизни:

- экспорт и импорт, товары и услуги;
- валюта цены и валюта платежа иногда разные — цена в долларах, платёж в
  юанях: ради этого поля и разведены;
- суммы по обе стороны порога постановки на учёт: часть без учёта вовсе,
  часть «документы по запросу», половина — с УНК;
- все состояния: проекты с незаполненными полями, заключённые без учёта,
  на учёте, исполняемые, исполненные, снятые с учёта, расторгнутые;
- способы расчёта: перевод, аккредитив на разных стадиях, ЦФА на разных
  шагах, встречная поставка;
- ведомость: документы и платежи; у части экспортных контрактов срок
  оплаты прошёл, а денег нет — просроченная репатриация.

Главный участник витрины — российская сторона в двух десятках контрактов
от имени своих организаций, остальные видны в режиме администратора.

Повторный запуск ничего не добавляет.
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

# Страна: (код, контрагенты, валюта платежа, приблизительный курс к рублю).
COUNTRIES = {
    'CN': (['Qingdao Haixin Trading Co., Ltd.', 'Harbin Longjiang Agro Import Co., Ltd.',
            'Zhejiang Tianyu Machinery Co., Ltd.', 'Shenzhen Brightway Electronics Ltd.',
            'Heilongjiang Sino-Russian Timber Co.'], 'CNY', 12.6),
    'IN': (['Sharma Agro Exports Pvt. Ltd.', 'Mumbai Textile Mills Ltd.',
            'Chennai Spice Traders Pvt. Ltd.', 'Pune Engineering Works Ltd.'], 'INR', 1.07),
    'AE': (['Al Noor General Trading LLC', 'Gulf Bridge Logistics FZE',
            'Emirates Food Supply LLC'], 'AED', 24.4),
    'TR': (['Anadolu Makina Sanayi A.S.', 'Izmir Tekstil Ticaret Ltd. Sti.',
            'Ege Meyve Ihracat A.S.'], 'TRY', 2.6),
    'KZ': (['ТОО «Астана Агро Трейд»', 'ТОО «Каспий Логистик»', 'ТОО «Алматы Техснаб»'],
           'KZT', 0.18),
    'BY': (['ОАО «Гомельский химический завод»', 'ООО «Минск Агропродукт»',
            'ОАО «Бобруйскагромаш»'], 'BYN', 28.0),
    'BR': (['Agro Parana Comercio Ltda.', 'Sao Paulo Coffee Exporters S.A.'], 'BRL', 16.2),
    'ZA': (['Cape Fruit Exporters (Pty) Ltd', 'Durban Mining Supply (Pty) Ltd'], 'ZAR', 5.0),
    'UZ': (['ООО «Ташкент Текстиль Групп»', 'ООО «Самарканд Фрукт Экспорт»'], 'RUB', 1.0),
    'AM': (['ООО «Ереван Фуд Импорт»', 'ЗАО «Гюмри Строй»'], 'RUB', 1.0),
    'KG': (['ОсОО «Бишкек Агро»', 'ОсОО «Ош Трейд Центр»'], 'RUB', 1.0),
    'EG': (['Nile Valley Agro Trading S.A.E.', 'Cairo Industrial Supply Co.'], 'USD', 90.0),
    'IR': (['Pars Agro Industry Co.', 'Tabriz Machinery Trading Co.'], 'CNY', 12.6),
    'VN': (['Saigon Seafood Export JSC', 'Hanoi Garment Corporation'], 'CNY', 12.6),
    'RS': (['Beograd Agrar d.o.o.', 'Novi Sad Pack d.o.o.'], 'EUR', 98.0),
}

EXPORT_GOODS = [
    ('Поставка подсолнечного масла нерафинированного', 'Масло подсолнечное нерафинированное, ГОСТ 1129-2013, 1-й сорт, наливом в флекситанках, {q} т'),
    ('Поставка пшеницы продовольственной', 'Пшеница продовольственная 4-го класса, протеин не менее 12,5 %, {q} т'),
    ('Поставка пиломатериалов хвойных пород', 'Доска обрезная сосна, 50×150×6000 мм, сорт 1–3, камерной сушки, {q} м³'),
    ('Поставка мёда липового', 'Мёд натуральный липовый, фасовка бочки 300 кг, {q} т'),
    ('Поставка льняного волокна', 'Волокно льняное длинное, номер 12, в кипах, {q} т'),
    ('Поставка кондитерских изделий', 'Конфеты шоколадные ассорти, коробки 250 г, {q} паллет'),
    ('Поставка минеральных удобрений', 'Аммиачная селитра марки Б, мешки 50 кг, {q} т'),
    ('Поставка металлопроката', 'Лист горячекатаный 3 мм, сталь 09Г2С, {q} т'),
    ('Поставка гречневой крупы', 'Крупа гречневая ядрица, 1-й сорт, мешки 50 кг, {q} т'),
]
IMPORT_GOODS = [
    ('Закупка станков с ЧПУ', 'Фрезерный обрабатывающий центр с ЧПУ, стол 1000×500 мм, {q} шт.'),
    ('Закупка запчастей для сельхозтехники', 'Подшипники, ремни, ножи жаток по спецификации, {q} позиций'),
    ('Закупка хлопковой ткани', 'Ткань хлопковая бязь, плотность 142 г/м², {q} тыс. м'),
    ('Закупка свежих фруктов', 'Мандарины калибр 1–2, ящики 10 кг, {q} т'),
    ('Закупка чая и специй', 'Чай чёрный листовой CTC и специи по спецификации, {q} т'),
    ('Закупка упаковочного оборудования', 'Линия фасовки в дой-пак, производительность 40 уп/мин, {q} шт.'),
    ('Закупка электронных компонентов', 'Микроконтроллеры и силовые модули по спецификации, {q} тыс. шт.'),
    ('Закупка кофе зелёного', 'Кофе зелёный арабика, мешки 60 кг, {q} т'),
]
EXPORT_SERVICES = [
    ('Разработка программного обеспечения', 'Разработка модуля учёта склада, 3 этапа, {q} чел.-мес.'),
    ('Инжиниринг и проектирование', 'Проект реконструкции цеха, стадии П и Р, {q} листов'),
    ('Обучение персонала заказчика', 'Курс по эксплуатации оборудования, {q} слушателей'),
    ('Дизайн и вёрстка каталога', 'Каталог продукции на трёх языках, {q} полос'),
]
IMPORT_SERVICES = [
    ('Шеф-монтаж оборудования', 'Шеф-монтаж и пусконаладка линии, {q} дней'),
    ('Консультирование по сертификации', 'Сопровождение сертификации продукции для рынка страны, {q} часов'),
    ('Международная перевозка грузов', 'Перевозка автотранспортом, {q} рейсов'),
]

BANKS = [('ПАО Сбербанк', '1481'), ('Банк ВТБ (ПАО)', '1000'), ('АО «Альфа-Банк»', '1326'),
         ('ПАО «Промсвязьбанк»', '3251'), ('Банк ГПБ (АО)', '354'), ('АО «Россельхозбанк»', '3349')]

FOREIGN_BANKS = ['Bank of China', 'Industrial and Commercial Bank of China', 'State Bank of India',
                 'Emirates NBD', 'Ziraat Bankasi', 'Halyk Bank', 'Беларусбанк', 'Banco do Brasil']


def _pick_state(rnd):
    return rnd.choices(
        ['draft', 'signed', 'registered', 'performing', 'done', 'closed', 'cancelled'],
        weights=[10, 9, 14, 30, 15, 13, 9])[0]


def load_trade(env, login='dashkevich', target=130):
    if 'coop.trade.contract' not in env:
        return 0
    Contract = env['coop.trade.contract'].sudo().with_context(
        tracking_disable=True, mail_create_nolog=True, mail_notrack=True)
    if Contract.search_count([], limit=1):
        _logger.info('Международные сделки: уже наполнено, пропускаю')
        return 0
    rnd = random.Random(20260925 + 392)
    today = date.today()
    Partner = env['res.partner'].sudo()
    Currency = env['res.currency'].sudo().with_context(active_test=False)
    Country = env['res.country'].sudo()

    # Внешней торговлей не занимаются товарищества собственников жилья,
    # некоммерческие фонды и АНО — их в российские стороны не берём.
    def trades(partner):
        return not (partner.name or '').startswith(('ТСЖ', 'ТСН', 'АНО', 'Фонд', 'НКО'))

    orgs = Partner.search([('coop_is_participant', '=', True),
                           ('is_company', '=', True)]).filtered(trades)
    if len(orgs) < 10:
        _logger.info('Международные сделки: нечего наполнять')
        return 0
    showcase_user = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    showcase_orgs = (showcase_user.coop_actor_partner_ids
                     .filtered(lambda p: p.is_company and trades(p))) if showcase_user else Partner
    operators = env['coop.cfa.operator'].sudo().search([]) if 'coop.cfa.operator' in env else None

    def currency(code):
        return Currency.search([('name', '=', code)], limit=1)

    usd = currency('USD')
    rub = currency('RUB')
    made = 0
    for index in range(target):
        code = rnd.choice(list(COUNTRIES))
        names, pay_code, rate = COUNTRIES[code]
        country = Country.with_context(lang='ru_RU').search([('code', '=', code)], limit=1)
        pay = currency(pay_code) or rub
        # Цена в долларах, платёж в валюте страны — у каждого пятого: ради
        # этого поля валюты цены и платежа и разведены (п. 2 ст. 317 ГК).
        if pay_code not in ('RUB', 'USD', 'EUR') and rnd.random() < 0.2 and usd:
            price, price_rate = usd, 90.0
        else:
            price, price_rate = pay, rate

        direction = rnd.choices(
            ['export_goods', 'import_goods', 'export_services', 'import_services'],
            weights=[45, 32, 13, 10])[0]
        pool = {'export_goods': EXPORT_GOODS, 'import_goods': IMPORT_GOODS,
                'export_services': EXPORT_SERVICES, 'import_services': IMPORT_SERVICES}[direction]
        title, subject = rnd.choice(pool)
        # Сумма в рублях — по обе стороны порога.
        band = rnd.random()
        if band < 0.18:
            amount_rub = rnd.randint(150, 950) * 1000
        elif band < 0.45:
            amount_rub = rnd.randint(1100, 9500 if direction.startswith('export') else 2900) * 1000
        else:
            amount_rub = rnd.randint(3100 if direction.startswith('import') else 10200,
                                     rnd.choice([20000, 60000, 180000])) * 1000
        amount = round(amount_rub / price_rate, -2 if amount_rub > 5_000_000 else 0)

        state = _pick_state(rnd)
        signed = today - timedelta(days=rnd.randint(5, 540))
        performance = signed + timedelta(days=rnd.randint(30, 200))
        payment_due = performance + timedelta(days=rnd.choice([10, 30, 45, 60, 90]))
        if index < 22 and showcase_orgs:
            resident = showcase_orgs[index % len(showcase_orgs)]
        else:
            resident = rnd.choice(orgs)
        foreign = rnd.choice(names)
        bank, bank_reg = rnd.choice(BANKS)
        settlement = rnd.choices(['transfer', 'lc', 'cfa', 'barter'], weights=[52, 25, 13, 10])[0]
        complete = state != 'draft' or rnd.random() < 0.4

        vals = {
            'name': '%s — %s' % (title, country.name),
            'direction': direction,
            'resident_id': resident.id,
            'foreign_name': foreign,
            'foreign_country_id': country.id,
            'foreign_details': ('%s\nРег. № %s\n%s' % (
                foreign, rnd.randint(10 ** 8, 10 ** 9 - 1), rnd.choice(FOREIGN_BANKS)))
            if complete or rnd.random() < 0.5 else False,
            'subject': subject.format(q=rnd.choice([5, 12, 20, 40, 60, 120, 250, 500]))
            if complete or rnd.random() < 0.6 else False,
            'price_currency_id': price.id,
            'payment_currency_id': pay.id,
            'amount': amount,
            'amount_rub': amount_rub,
            'signed_on': signed if state != 'draft' else False,
            'performance_date': performance if complete or rnd.random() < 0.5 else False,
            'payment_due': payment_due if complete else False,
            'governing_law': rnd.choices(['ru', 'counterparty', 'third'], weights=[70, 22, 8])[0]
            if complete else False,
            'dispute_forum': rnd.choices(['mkas', 'ru_court', 'foreign_arbitration'],
                                         weights=[55, 33, 12])[0] if complete else False,
            'incoterms': rnd.choice(['FCA', 'CPT', 'DAP', 'EXW', 'CIF', 'FOB', 'DDP'])
            if direction.endswith('_goods') and complete else False,
            'incoterms_place': rnd.choice(['Новороссийск', 'Забайкальск', 'Владивосток',
                                           'Мытищи', 'Бандар-Аббас', 'Шанхай'])
            if direction.endswith('_goods') and complete else False,
            'bank_name': bank if state != 'draft' else False,
            'settlement': settlement,
            'state': state,
        }
        needs_unk = amount_rub >= (10_000_000 if direction.startswith('export') else 3_000_000)
        if needs_unk and state in ('registered', 'performing', 'done', 'closed'):
            vals['unk'] = '%s%04d/%s/0000/%d/1' % (
                signed.strftime('%y%m'), index + 1, bank_reg,
                1 if direction.startswith('export') else 2)
            vals['unk_on'] = signed + timedelta(days=rnd.randint(1, 5))
        if settlement == 'lc':
            vals.update({
                'lc_issuing_bank': rnd.choice(FOREIGN_BANKS) if direction.startswith('export') else bank,
                'lc_advising_bank': bank if direction.startswith('export') else rnd.choice(FOREIGN_BANKS),
                'lc_amount': amount,
                'lc_expiry': performance + timedelta(days=45),
                'lc_documents': 'Коммерческий инвойс, транспортная накладная, '
                                'сертификат происхождения, упаковочный лист',
                'lc_state': {'draft': False, 'signed': 'requested', 'registered': 'opened',
                             'performing': rnd.choice(['confirmed', 'documents']),
                             'done': 'paid', 'closed': 'paid',
                             'cancelled': 'expired'}[state],
            })
        if settlement == 'cfa' and operators:
            vals.update({
                'cfa_operator_id': rnd.choice(operators).id,
                'cfa_step': {'draft': False, 'signed': 'issue', 'registered': 'access',
                             'performing': rnd.choice(['access', 'transfer']),
                             'done': 'redeem', 'closed': 'redeem', 'cancelled': 'issue'}[state],
            })

        # Ведомость: документы и платежи по исполнению.
        docs, pays = [], []
        if state in ('performing', 'done', 'closed'):
            parts = rnd.randint(1, 4)
            share = 1.0 if state in ('done', 'closed') else rnd.uniform(0.2, 0.9)
            shipped = round(amount * share, 2)
            step = (performance - signed).days // (parts + 1) or 1
            for n in range(parts):
                when = signed + timedelta(days=step * (n + 1))
                if when > today:
                    break
                docs.append((0, 0, {
                    'date': when,
                    'kind': ('declaration' if direction.endswith('_goods') else 'act')
                    if n % 2 == 0 else 'invoice',
                    'number': '%s-%d' % (rnd.randint(1000, 9999), n + 1),
                    'amount': round(shipped / parts, 2),
                }))
            late_export = (direction.startswith('export') and state == 'performing'
                           and rnd.random() < 0.35)
            if state in ('done', 'closed'):
                paid = shipped
            elif late_export:
                paid = round(shipped * rnd.uniform(0, 0.5), 2)
                vals['payment_due'] = today - timedelta(days=rnd.randint(3, 60))
            else:
                paid = round(shipped * rnd.uniform(0.3, 1.0), 2)
            if paid:
                count = rnd.randint(1, 3)
                for n in range(count):
                    pays.append((0, 0, {
                        'date': min(today, signed + timedelta(days=rnd.randint(10, 200))),
                        'amount': round(paid / count, 2),
                        'note': 'Аванс' if n == 0 and count > 1 else 'Оплата по контракту',
                    }))
        vals['document_ids'] = docs
        vals['payment_ids'] = pays
        Contract.create(vals)
        made += 1

    _logger.info('Международные сделки: %s контрактов', made)
    return made


def repair_trade_names(env):
    """Страна в названии контракта — по-русски.

    Первый прогон брал название страны без языка, и в каталоге стояло
    «Поставка гречневой крупы — Armenia». Повторный запуск ничего не меняет.
    """
    if 'coop.trade.contract' not in env:
        return 0
    fixed = 0
    for contract in env['coop.trade.contract'].sudo().with_context(
            tracking_disable=True).search([]):
        english = contract.foreign_country_id.with_context(lang='en_US').name
        russian = contract.foreign_country_id.with_context(lang='ru_RU').name
        suffix = ' — %s' % english
        if english != russian and (contract.name or '').endswith(suffix):
            contract.name = contract.name[:-len(suffix)] + ' — %s' % russian
            fixed += 1
    if fixed:
        _logger.info('Международные сделки: страна по-русски в %s названиях', fixed)
    return fixed

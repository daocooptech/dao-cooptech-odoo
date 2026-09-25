# -*- coding: utf-8 -*-
"""Бартер — объявления и обмены (решение 412, Н7).

Каталог наполняется как действующая площадка:

- вещи, уже выставленные в «Ресурсах», — со снимком оттуда и только с
  собственным названием (шаблонных копий там по десятку); и около ста
  семидесяти своих — от работы и уроков до сена и снегохода, каждое по
  разу, без снимка — значком категории; в каталоге «меняю» остаётся
  полторы сотни, остальные — в обмене или обменяны;
- «хочу взамен» — одна-три категории и у половины свои слова;
- обмены во всех состояниях: предложенные (часть — с согласием одной
  стороны), исполняемые (сделки на разных шагах, одна — в споре),
  завершённые (акты, отзывы, история прав ресурса), отклонённые и
  отменённые; полтора десятка — цепочки на троих.

Повторный запуск ничего не добавляет.
"""
import logging
import random
import re
from datetime import date, datetime, timedelta

_logger = logging.getLogger(__name__)

VERB = re.compile(r'^(Продам|Продаю|Продаём|Продаем|Продаётся|Сдам|Сдаю|Отдам|Отдаю|Куплю|Ищу)\b')

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
    # Работа и услуги
    ('services', 'Покрою крышу металлочерепицей', 'до 120 м²', 40000, 90000),
    ('services', 'Сварочные работы на выезде', '8 часов', 8000, 16000),
    ('services', 'Вспашу и продискую огород мотоблоком', 'до 15 соток', 3000, 7000),
    ('services', 'Ремонт бензо- и электроинструмента', 'по объёму', 1500, 6000),
    ('services', 'Перевезу груз на «Газели» по области', 'рейс', 4000, 9000),
    ('services', 'Сложу печь-каменку для бани', 'одна печь', 35000, 70000),
    ('services', 'Бухгалтерия ИП на УСН за квартал', 'квартал', 6000, 12000),
    ('services', 'Покраска забора и фасада', 'до 60 м²', 12000, 25000),
    ('services', 'Электромонтаж в частном доме', 'до 10 точек', 10000, 22000),
    ('services', 'Уход за садом: обрезка, покос, листва', 'сезон', 15000, 30000),
    ('services', 'Фотосъёмка мероприятия', '4 часа', 8000, 15000),
    ('services', 'Сайт-визитка для кооператива или фермы', 'под ключ', 20000, 45000),
    ('services', 'Выкопаю траншею под водопровод', 'до 30 м', 9000, 18000),
    ('services', 'Соберу и установлю теплицу', 'одна теплица', 5000, 9000),
    ('services', 'Ремонт стиральных машин и холодильников', 'выезд', 2000, 5000),
    ('services', 'Шиномонтаж грузовых и сельхозшин', 'комплект', 3000, 7000),
    ('services', 'Пошив штор и ремонт одежды', 'по объёму', 2000, 6000),
    ('services', 'Стрижка и укладка на дому', '3 визита', 2500, 4500),
    ('services', 'Уборка дома после ремонта', 'до 100 м²', 6000, 12000),
    ('services', 'Заточка цепей, ножей, ножниц', 'по объёму', 800, 2500),
    ('services', 'Настрою компьютер и домашнюю сеть', 'выезд', 2000, 5000),
    ('services', 'Спил аварийных деревьев', '2 дерева', 8000, 20000),
    ('services', 'Колка и укладка дров', '10 м³', 6000, 10000),
    ('services', 'Плитка и затирка в ванной', 'до 20 м²', 15000, 30000),
    ('services', 'Посижу с пожилым человеком днём', 'неделя', 5000, 9000),
    ('services', 'Ветеринар на выезд к скоту', 'выезд', 2500, 5000),
    ('services', 'Отремонтирую забор из профлиста', 'до 20 м', 10000, 20000),
    ('services', 'Монтаж видеонаблюдения на участке', '4 камеры', 9000, 16000),
    ('services', 'Вывоз мусора самосвалом', 'рейс', 5000, 9000),
    ('services', 'Ремонт и регулировка пластиковых окон', 'до 5 окон', 3000, 7000),
    # Обучение и консультации
    ('teaching', 'Уроки английского для школьника', '8 занятий', 6000, 12000),
    ('teaching', 'Научу пчеловодству: сезон с наставником', '6 выездов', 15000, 25000),
    ('teaching', 'Консультация агронома по севообороту', '2 часа', 3000, 6000),
    ('teaching', 'Курс работы на токарном станке', '10 занятий', 12000, 20000),
    ('teaching', 'Репетитор по математике, ОГЭ', '10 занятий', 8000, 15000),
    ('teaching', 'Консультация юриста по договору', '1 час', 2500, 5000),
    ('teaching', 'Уроки игры на гитаре', '8 занятий', 5000, 9000),
    ('teaching', 'Научу вести учёт в таблицах', '4 занятия', 3000, 6000),
    ('teaching', 'Курс сыроделия в домашних условиях', '3 занятия', 4000, 8000),
    ('teaching', 'Подготовка к экзамену по вождению', '6 занятий', 6000, 10000),
    ('teaching', 'Консультация по оформлению ИП и самозанятости', '1 час', 1500, 3500),
    ('teaching', 'Мастер-класс по гончарному делу', '2 занятия', 3000, 6000),
    ('teaching', 'Логопед для дошкольника', '8 занятий', 7000, 12000),
    ('teaching', 'Научу катать свечи из вощины', '2 занятия', 2500, 4500),
    # Ремесло и хендмейд
    ('craft', 'Вязаные шерстяные носки', '5 пар', 2500, 4500),
    ('craft', 'Деревянная посуда ручной работы', 'набор', 3000, 8000),
    ('craft', 'Плетёные корзины из лозы', '3 шт.', 3000, 6000),
    ('craft', 'Керамические кружки ручной лепки', '6 шт.', 4000, 7000),
    ('craft', 'Кованые садовые фонари', '2 шт.', 9000, 18000),
    ('craft', 'Лоскутное одеяло', 'одно', 7000, 14000),
    ('craft', 'Свечи из пчелиного воска', '20 шт.', 2000, 4000),
    ('craft', 'Мыло ручной работы на травах', '15 кусков', 2000, 3500),
    ('craft', 'Резные наличники на окна', '4 комплекта', 16000, 30000),
    ('craft', 'Кожаный ремень и кошелёк на заказ', 'комплект', 4000, 7000),
    ('craft', 'Валенки ручной валки', '2 пары', 5000, 9000),
    ('craft', 'Скворечники и кормушки', '10 шт.', 3000, 5000),
    # Площади и жильё на время
    ('space', 'Гараж с ямой на месяц', 'месяц', 4000, 8000),
    ('space', 'Место на складе под поддоны', '10 паллет на месяц', 6000, 12000),
    ('space', 'Дом у озера на выходные', '2 ночи', 8000, 15000),
    ('space', 'Цех 60 м² с трёхфазным током на неделю', 'неделя', 10000, 20000),
    ('space', 'Комната для гостей на неделю', '7 ночей', 7000, 12000),
    ('space', 'Сухой подвал под овощи на зиму', 'сезон', 3000, 6000),
    ('space', 'Участок под огород на сезон', '6 соток', 5000, 10000),
    ('space', 'Кабинет в центре города на день', '1 день', 2000, 4000),
    ('space', 'Место под пасеку у гречишного поля', 'сезон', 6000, 12000),
    # Семена и саженцы
    ('seeds', 'Саженцы яблони, районированные сорта', '10 шт.', 4000, 8000),
    ('seeds', 'Рассада томатов и перца', '60 шт.', 2500, 5000),
    ('seeds', 'Семенной картофель «Гала»', '200 кг', 8000, 14000),
    ('seeds', 'Черенки смородины и крыжовника', '30 шт.', 2000, 4000),
    ('seeds', 'Луковицы тюльпанов и нарциссов', '100 шт.', 3000, 5000),
    ('seeds', 'Саженцы малины ремонтантной', '40 шт.', 3000, 6000),
    ('seeds', 'Семена сидератов: горчица и фацелия', '10 кг', 2000, 4000),
    ('seeds', 'Туи и можжевельник для живой изгороди', '15 шт.', 6000, 12000),
    ('seeds', 'Клубника, усы сортовые', '100 шт.', 2500, 4500),
    # Сельхозпродукция и корма
    ('farm', 'Сено в тюках', '100 тюков', 18000, 30000),
    ('farm', 'Зерно фуражное (пшеница)', '1 т', 14000, 20000),
    ('farm', 'Навоз перепревший', '5 т', 5000, 9000),
    ('farm', 'Козье молоко, еженедельно', 'месяц', 6000, 10000),
    ('farm', 'Цыплята-бройлеры суточные', '50 шт.', 4000, 7000),
    ('farm', 'Ячмень кормовой', '2 т', 22000, 30000),
    ('farm', 'Солома в рулонах', '30 рулонов', 12000, 18000),
    ('farm', 'Кролики породы «фландр»', '6 голов', 6000, 10000),
    ('farm', 'Индюшата суточные', '20 шт.', 5000, 8000),
    ('farm', 'Пчелопакеты карпатской пчелы', '3 шт.', 15000, 21000),
    ('farm', 'Комбикорм для несушек', '400 кг', 9000, 13000),
    ('farm', 'Яйцо инкубационное', '120 шт.', 3000, 5000),
    ('farm', 'Тёлочка, 4 месяца', 'одна', 35000, 50000),
    # Продукты питания
    ('food', 'Мёд липовый', '20 кг', 12000, 18000),
    ('food', 'Варенье и соленья домашние', '15 банок', 3000, 6000),
    ('food', 'Сыр козий выдержанный', '5 кг', 6000, 10000),
    ('food', 'Иван-чай ферментированный', '3 кг', 4000, 7000),
    ('food', 'Сушёные грибы: белые и подберёзовики', '2 кг', 6000, 10000),
    ('food', 'Клюква и брусника, заморозка', '15 кг', 5000, 8000),
    ('food', 'Домашняя тушёнка', '20 банок', 7000, 11000),
    ('food', 'Хлеб на закваске, еженедельно', 'месяц', 3000, 5000),
    ('food', 'Облепиховое масло холодного отжима', '2 л', 3000, 5000),
    ('food', 'Копчёная рыба: лещ и сом', '8 кг', 6000, 10000),
    ('food', 'Мука цельнозерновая с мельницы', '50 кг', 3500, 5500),
    ('food', 'Яблоки осенние, сортовые', '200 кг', 8000, 14000),
    ('food', 'Кедровый орех очищенный', '5 кг', 7000, 11000),
    # Детские товары
    ('kids', 'Коляска 2 в 1, после одного ребёнка', 'одна', 8000, 16000),
    ('kids', 'Детская одежда 1–3 года, пакетом', '30 вещей', 3000, 6000),
    ('kids', 'Конструктор и развивающие игрушки', 'коробка', 3000, 7000),
    ('kids', 'Автокресло 9–18 кг', 'одно', 3000, 6000),
    ('kids', 'Детский велосипед с боковыми колёсами', 'один', 2500, 5000),
    ('kids', 'Кроватка-манеж с матрасом', 'одна', 4000, 8000),
    ('kids', 'Школьная форма и рюкзак', 'комплект', 3000, 6000),
    ('kids', 'Санки-коляска и ледянки', 'набор', 1500, 3000),
    # Одежда и обувь
    ('clothes', 'Рабочая одежда и спецобувь', '6 комплектов', 6000, 12000),
    ('clothes', 'Зимний пуховик, новый', 'один', 6000, 11000),
    ('clothes', 'Костюм-тройка, 52 размер', 'один', 4000, 8000),
    ('clothes', 'Охотничий костюм мембранный', 'один', 7000, 13000),
    ('clothes', 'Женские сапоги кожаные, 38', 'одна пара', 3000, 6000),
    ('clothes', 'Свадебное платье, после химчистки', 'одно', 8000, 18000),
    # Хобби и спорт
    ('hobby', 'Палатка четырёхместная и спальники', 'комплект', 7000, 14000),
    ('hobby', 'Спиннинги и катушки', '3 комплекта', 5000, 12000),
    ('hobby', 'Лодка ПВХ с мотором', 'одна', 45000, 90000),
    ('hobby', 'Беговые лыжи с ботинками', '2 комплекта', 4000, 8000),
    ('hobby', 'Гантели и штанга разборные', 'набор', 5000, 9000),
    ('hobby', 'Настольные игры, коллекция', '12 коробок', 5000, 10000),
    ('hobby', 'Акустическое пианино', 'одно', 10000, 25000),
    ('hobby', 'Горный велосипед, рама 19', 'один', 12000, 22000),
    # Электроника
    ('electronics', 'Ноутбук для учёбы', 'один', 18000, 30000),
    ('electronics', 'Смартфон, в хорошем состоянии', 'один', 9000, 18000),
    ('electronics', 'Монитор 27 дюймов', 'один', 8000, 14000),
    ('electronics', 'Принтер лазерный с запасом картриджей', 'один', 5000, 9000),
    ('electronics', 'Планшет для ребёнка', 'один', 6000, 11000),
    ('electronics', 'Рация и навигатор для рыбалки', 'комплект', 5000, 10000),
    # Для дома и дачи
    ('home', 'Дрова берёзовые колотые', '5 м³', 12000, 18000),
    ('home', 'Стиральная машина, рабочая', 'одна', 6000, 12000),
    ('home', 'Диван раскладной', 'один', 7000, 14000),
    ('home', 'Газовая плита четырёхконфорочная', 'одна', 4000, 8000),
    ('home', 'Бочки пластиковые 200 л', '6 шт.', 3000, 5000),
    ('home', 'Шкаф-купе, разобранный', 'один', 6000, 12000),
    ('home', 'Садовые качели', 'одни', 5000, 9000),
    ('home', 'Ковры шерстяные', '3 шт.', 4000, 9000),
    ('home', 'Печь-буржуйка для гаража', 'одна', 5000, 9000),
    ('home', 'Посуда и кухонная утварь, коробкой', 'коробка', 2000, 4000),
    # Стройматериалы
    ('building', 'Доска обрезная, остатки со стройки', '2 м³', 20000, 32000),
    ('building', 'Кирпич б/у, очищенный', '1500 шт.', 9000, 15000),
    ('building', 'Профнастил, остатки', '40 листов', 15000, 25000),
    ('building', 'Утеплитель минвата', '12 упаковок', 8000, 13000),
    ('building', 'Тротуарная плитка', '30 м²', 12000, 20000),
    ('building', 'Цемент М500', '20 мешков', 7000, 10000),
    ('building', 'Окна ПВХ после замены', '4 шт.', 6000, 12000),
    ('building', 'Брус 150×150', '3 м³', 30000, 45000),
    ('building', 'Щебень гранитный', '10 т', 12000, 18000),
    # Инструмент
    ('tools', 'Бетономешалка 180 л', 'одна', 9000, 15000),
    ('tools', 'Набор столярного инструмента', 'комплект', 8000, 15000),
    ('tools', 'Бензопила «Штиль»', 'одна', 12000, 20000),
    ('tools', 'Сварочный инвертор с масками', 'комплект', 7000, 12000),
    ('tools', 'Строительные леса', '12 секций', 15000, 25000),
    ('tools', 'Перфоратор и шуруповёрт', 'набор', 6000, 11000),
    ('tools', 'Культиватор ручной и тяпки', 'набор', 2000, 4000),
    # Оборудование
    ('equipment', 'Инкубатор на 100 яиц', 'один', 7000, 12000),
    ('equipment', 'Холодильная витрина', 'одна', 20000, 40000),
    ('equipment', 'Пресс для сока, ручной', 'один', 6000, 10000),
    ('equipment', 'Коптильня горячего копчения', 'одна', 8000, 15000),
    ('equipment', 'Дистиллятор для эфирных масел', 'один', 15000, 25000),
    ('equipment', 'Швейная машина промышленная', 'одна', 15000, 30000),
    ('equipment', 'Генератор бензиновый 5 кВт', 'один', 20000, 35000),
    # Техника и транспорт
    ('vehicles', 'Прицеп к легковому автомобилю', 'один', 30000, 55000),
    ('vehicles', 'Мопед для поездок по селу', 'один', 25000, 40000),
    ('vehicles', 'Снегоход «Буран», на ходу', 'один', 80000, 130000),
    ('vehicles', 'Навесной плуг к мотоблоку', 'один', 5000, 9000),
    ('vehicles', 'Колёса зимние на 16', 'комплект', 12000, 20000),
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


DEMO_VERSION = '2'


def _reset_first_fill(env):
    """Снять первое наполнение (25.09.2026, `7079686`) — оно брало из
    «Ресурсов» шаблонные копии («Сдам бетономешалку на выходные» — 11 раз)
    и свои объявления по два-три раза.

    Снимается только наполнение: если хоть одно объявление или обмен
    завёл живой человек, ничего не трогаем. Сделки обмена, их отзывы,
    записи истории прав и извещения уходят вместе с ним, счётчики сделок
    сторон пересчитываются. Отметка версии в параметрах — второй раз не
    сработает."""
    Param = env['ir.config_parameter'].sudo()
    if Param.get_param('coop_barter.demo_version') == DEMO_VERSION:
        return False
    cr = env.cr
    cr.execute('SELECT count(*) FROM coop_barter_offer WHERE create_uid <> 1')
    live = cr.fetchone()[0]
    cr.execute('SELECT count(*) FROM coop_barter_exchange WHERE create_uid <> 1')
    live += cr.fetchone()[0]
    if live:
        _logger.warning('Бартер: есть записи участников (%s) — наполнение не пересобираю', live)
        Param.set_param('coop_barter.demo_version', DEMO_VERSION)
        return False
    cr.execute('SELECT id, party_a_id, party_b_id FROM coop_deal '
               'WHERE coop_barter_exchange_id IS NOT NULL')
    rows = cr.fetchall()
    deal_ids = [r[0] for r in rows] or [0]
    partners = {p for r in rows for p in r[1:] if p}
    cr.execute('SELECT id FROM coop_barter_exchange')
    exchange_ids = [r[0] for r in cr.fetchall()] or [0]
    cr.execute('SELECT id FROM coop_barter_offer')
    offer_ids = [r[0] for r in cr.fetchall()] or [0]
    cr.execute('SELECT id FROM coop_deal_review WHERE deal_id = ANY(%s)', [deal_ids])
    review_ids = [r[0] for r in cr.fetchall()] or [0]
    targets = [('coop.deal', deal_ids), ('coop.barter.exchange', exchange_ids),
               ('coop.barter.offer', offer_ids), ('coop.deal.review', review_ids)]
    for model, ids in targets:
        cr.execute('DELETE FROM mail_message WHERE model = %s AND res_id = ANY(%s)', [model, ids])
        cr.execute('DELETE FROM mail_followers WHERE res_model = %s AND res_id = ANY(%s)',
                   [model, ids])
        cr.execute('DELETE FROM coop_notification WHERE res_model = %s AND res_id = ANY(%s)',
                   [model, ids])
    cr.execute("DELETE FROM coop_favorite WHERE res_model = 'coop.barter.offer'")
    cr.execute('DELETE FROM coop_resource_transfer WHERE deal_id = ANY(%s)', [deal_ids])
    cr.execute('DELETE FROM coop_deal_review WHERE id = ANY(%s)', [review_ids])
    cr.execute('DELETE FROM coop_deal WHERE id = ANY(%s)', [deal_ids])
    cr.execute('DELETE FROM coop_barter_leg')
    cr.execute('DELETE FROM coop_barter_exchange')
    cr.execute('DELETE FROM coop_barter_offer')
    env.invalidate_all()
    if partners:
        env['res.partner'].sudo().browse(list(partners))._coop_recompute_deal_stats()
    _logger.info('Бартер: первое наполнение снято — сделок %s, обменов %s, объявлений %s',
                 len(rows), len(exchange_ids), len(offer_ids))
    return True


def load_barter(env, login='dashkevich'):
    if 'coop.barter.offer' not in env:
        return 0
    _reset_first_fill(env)
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
    # Только вещи с собственным названием: шаблонные «Сдам бетономешалку на
    # выходные» стоят в «Ресурсах» по десятку раз, а копии одной строки
    # каталогом не считаются. И без глагола продажи — это обмен.
    names = {}
    for resource in resources:
        names[resource.name] = names.get(resource.name, 0) + 1
    own_titles = {title for _code, title, *_rest in OWN_OFFERS}
    picked = [r for r in resources
              if RESOURCE_CATEGORY.get(r.category_id.name) and names[r.name] == 1
              and not VERB.match(r.name) and r.name not in own_titles]
    rnd.shuffle(picked)
    resources = picked

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
    for code, title, qty, low, high in OWN_OFFERS:
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
    env['ir.config_parameter'].sudo().set_param('coop_barter.demo_version', DEMO_VERSION)
    _logger.info('Бартер: объявлений %s, обменов %s', len(made), exchanges)
    return len(made)


def _load_exchanges(env, rnd, offers, now):
    Exchange = env['coop.barter.exchange'].sudo().with_context(tracking_disable=True,
                                                               mail_create_nolog=True)
    Leg = env['coop.barter.leg'].sudo()
    free = [o for o in offers]
    rnd.shuffle(free)
    plan = (['proposed'] * 18 + ['proposed_half'] * 6 + ['agreed'] * 18 + ['done'] * 24
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

# -*- coding: utf-8 -*-
"""Производство организаций и техпроцесс на карточках ресурсов (решение 630).

Организации, которые выставили то, что сами делают (пельмени, цемент,
брус, мёд, молоко, дома…), включают приложение «Производство» и ведут в
нём то, что вёл бы живой технолог: участки, спецификации с составом и
операциями (у части операций — инструкция), выпуски партиями во всех
состояниях — готовые, в работе, запланированные, отменённые. Своё
объявление организация связывает со спецификацией; показ техпроцесса
включён у трёх из четырёх — у остальных блока на карточке нет, и это
тоже состояние (решение 374).

Витрина под `dashkevich` — его организация «Вектор Инжиниринг» с
утеплителем, показ включён.

Повторяемо: спецификация ищется по изделию и компании учёта, выпуск —
по номеру; уже заведённое пропускается. Жребий — от номера ресурса.
"""
import logging
import random
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

# Шаблон: слова в названии объявления → участки с операциями, изделия
# рядом (первое — само объявление), состав, единица и размер партии.
# Операция: (название, минут на партию, инструкция или None).
TEMPLATES = [
    {
        'words': ('пельмен',),
        'products': ('Пельмени домашней лепки', 'Вареники с картофелем', 'Манты с говядиной'),
        'components': ('Мука пшеничная', 'Говядина', 'Свинина', 'Лук репчатый', 'Яйцо куриное'),
        'uom': 'kg', 'qty': (40, 120),
        'stages': [
            ('Заготовочный цех', [
                ('Приёмка мяса и входной контроль', 30, 'Температура в толще не выше +4 °C, ветеринарное свидетельство из «Меркурия».'),
                ('Обвалка и жиловка', 60, 'Снять плёнки и хрящи, кусок — не больше 200 г.'),
                ('Приготовление фарша', 40, 'Говядина и свинина 1:1, лук 12 %, соль 1,5 %; решётка мясорубки 3 мм.'),
            ]),
            ('Цех лепки', [
                ('Замес теста', 25, 'Мука, вода +10 °C, яйцо; замес 12 минут, отлёжка 30 минут под плёнкой.'),
                ('Лепка на аппарате', 90, None),
                ('Шоковая заморозка', 45, 'Камера −35 °C, до −18 °C в центре изделия.'),
            ]),
            ('Упаковка', [
                ('Фасовка по 1 кг', 30, None),
                ('Маркировка «Честный знак»', 15, 'Код — на каждую пачку до выхода из цеха.'),
            ]),
        ],
    },
    {
        'words': ('цемент',),
        'products': ('Цемент М500', 'Цемент М400', 'Цемент М500 в биг-бэгах'),
        'components': ('Известняк', 'Глина', 'Гипсовый камень'),
        'uom': 't', 'qty': (20, 60),
        'stages': [
            ('Сырьевой цех', [
                ('Дробление известняка', 60, 'Фракция на выходе — до 25 мм; проверять сито каждую смену.'),
                ('Помол сырьевой смеси', 90, None),
            ]),
            ('Печь обжига', [
                ('Обжиг клинкера', 240, 'Зона спекания 1450 °C; температура и разрежение — в журнал каждый час.'),
                ('Охлаждение клинкера', 60, None),
            ]),
            ('Цементная мельница', [
                ('Помол с гипсом', 120, 'Гипс 4–5 %, удельная поверхность 3000–3500 см²/г.'),
                ('Испытание на марку', 30, 'Образцы-балочки, сжатие на 2-е и 28-е сутки.'),
            ]),
            ('Фасовка', [
                ('Фасовка в мешки по 50 кг', 45, None),
            ]),
        ],
    },
    {
        'words': ('брус', 'доск', 'пиломатериал'),
        'products': ('Брус 20×20', 'Доски обрезные 40×150', 'Пиломатериал обрезной', 'Рейка 20×40'),
        'components': ('Бревно сосновое', 'Антисептик'),
        'uom': 'm3', 'qty': (5, 25),
        'stages': [
            ('Лесопильный цех', [
                ('Окорка брёвен', 40, None),
                ('Распил на ленточной пиле', 90, 'Постав — по карте раскроя; развод зуба проверять каждые 4 часа.'),
            ]),
            ('Сушильная камера', [
                ('Камерная сушка до 12 %', 600, 'Режим мягкий, подъём температуры не быстрее 5 °C в час; влагомер — 3 замера на штабель.'),
            ]),
            ('Строгальный участок', [
                ('Строжка в размер', 60, None),
                ('Торцовка и сортировка', 40, 'Сорт — по ГОСТ 8486: сучки, трещины, обзол.'),
            ]),
            ('Склад готовой продукции', [
                ('Антисептирование и пакетирование', 30, None),
            ]),
        ],
    },
    {
        'words': ('арматур', 'профильн', 'металлочерепиц'),
        'products': ('Профильная труба стальная', 'Арматура А1-8', 'Металлочерепица', 'Уголок стальной 50×50'),
        'components': ('Рулонная сталь', 'Полимерное покрытие'),
        'uom': 't', 'qty': (5, 20),
        'stages': [
            ('Участок подготовки', [
                ('Продольная резка рулона', 45, 'Ширина штрипса — по заказу, допуск ±0,5 мм.'),
            ]),
            ('Профилегибочный стан', [
                ('Формовка профиля', 120, None),
                ('Сварка шва ТВЧ', 60, 'Контроль шва — ультразвук каждые 50 м.'),
                ('Калибровка', 30, None),
            ]),
            ('ОТК и упаковка', [
                ('Контроль геометрии', 20, None),
                ('Резка в мерные длины и увязка', 40, None),
            ]),
        ],
    },
    {
        'words': ('кирпич',),
        'products': ('Кирпич керамический М150', 'Кирпич облицовочный', 'Камень керамический 10,7 НФ'),
        'components': ('Глина', 'Песок', 'Опилки'),
        'uom': 'unit', 'qty': (5000, 20000),
        'stages': [
            ('Глинозапасник', [
                ('Вылёживание и рыхление глины', 120, None),
                ('Переработка на вальцах', 60, 'Зазор вальцов тонкого помола — 1–2 мм.'),
            ]),
            ('Формовочный участок', [
                ('Формовка на ленточном прессе', 90, 'Влажность массы 18–22 %.'),
                ('Резка бруса на сырец', 30, None),
            ]),
            ('Сушилка', [
                ('Сушка сырца', 1440, None),
            ]),
            ('Туннельная печь', [
                ('Обжиг', 1800, 'Максимум 980–1050 °C; охлаждение не быстрее 50 °C в час.'),
                ('Пакетирование на поддоны', 45, None),
            ]),
        ],
    },
    {
        'words': ('бетон',),
        'products': ('Бетон товарный М300', 'Бетон М200', 'Раствор кладочный М150'),
        'components': ('Цемент', 'Песок', 'Щебень', 'Пластификатор'),
        'uom': 'm3', 'qty': (8, 40),
        'stages': [
            ('Бетоносмесительный узел', [
                ('Дозирование цемента и заполнителей', 10, 'По рецепту в карте подбора состава; точность весов — 1 %.'),
                ('Перемешивание', 5, None),
                ('Проверка подвижности', 10, 'Осадка конуса П3 — 10–15 см.'),
            ]),
            ('Отгрузка', [
                ('Загрузка автобетоносмесителя', 10, None),
                ('Отбор образцов-кубов', 10, 'Серия из трёх кубов 100 мм на каждые 50 м³.'),
            ]),
        ],
    },
    {
        'words': ('утеплител',),
        'products': ('Утеплитель минеральная вата', 'Утеплитель минеральный', 'Плита фасадная базальтовая'),
        'components': ('Базальт', 'Связующее', 'Плёнка упаковочная'),
        'uom': 'm3', 'qty': (30, 120),
        'stages': [
            ('Плавильный участок', [
                ('Плавка базальта в вагранке', 120, 'Температура расплава 1500 °C; шихту подавать порциями.'),
            ]),
            ('Волокнообразование', [
                ('Раздув на центрифуге', 60, None),
                ('Нанесение связующего', 20, 'Расход — 2,5–3 % от массы волокна.'),
            ]),
            ('Камера полимеризации', [
                ('Полимеризация ковра', 45, None),
            ]),
            ('Резка и упаковка', [
                ('Резка на плиты', 30, None),
                ('Упаковка в плёнку', 20, None),
            ]),
        ],
    },
    {
        'words': ('картофел', 'коробка'),
        'products': ('Картофель урожая этого года', 'Коробка «Стандарт» · зелень и овощи', 'Морковь мытая'),
        'components': ('Тара — ящик', 'Сетка-мешок'),
        'uom': 'kg', 'qty': (200, 1500),
        'stages': [
            ('Поле и теплица', [
                ('Уборка урожая', 240, None),
                ('Сбор зелени', 60, 'Срезать утром до жары, сразу в тень.'),
            ]),
            ('Сортировочный цех', [
                ('Мойка', 60, None),
                ('Калибровка и отбраковка', 90, 'Отбраковка: гниль, механические повреждения, позеленение.'),
                ('Фасовка в тару', 60, None),
            ]),
            ('Холодильник', [
                ('Охлаждение до +4 °C', 120, None),
            ]),
        ],
    },
    {
        'words': ('мёд', 'мед '),
        'products': ('Мёд натуральный липовый', 'Мёд гречишный', 'Перга пчелиная'),
        'components': ('Банка стеклянная 1 л', 'Крышка', 'Этикетка'),
        'uom': 'kg', 'qty': (30, 80),
        'stages': [
            ('Пасека', [
                ('Осмотр ульев', 20, 'Дымарь, сетка; рамки с печаткой не меньше чем на две трети.'),
                ('Отбор запечатанных рамок', 20, None),
            ]),
            ('Медогонная', [
                ('Распечатка сот', 30, 'Нож подогреть, забрус собирать отдельно.'),
                ('Откачка на медогонке', 45, None),
                ('Процеживание', 15, None),
            ]),
            ('Фасовочная', [
                ('Розлив по 1 и 3 кг', 45, None),
                ('Этикетка с датой откачки и номером партии', 30, None),
            ]),
        ],
    },
    {
        'words': ('мука',),
        'products': ('Мука пшеничная высшего сорта', 'Мука пшеничная первого сорта', 'Отруби пшеничные'),
        'components': ('Зерно пшеницы', 'Мешок 50 кг'),
        'uom': 'kg', 'qty': (2000, 10000),
        'stages': [
            ('Элеватор', [
                ('Приёмка и анализ зерна', 30, 'Клейковина не ниже 28 %, влажность до 14 %.'),
                ('Очистка', 60, None),
            ]),
            ('Мельница', [
                ('Отволаживание', 480, None),
                ('Помол', 180, None),
                ('Просеивание', 60, None),
            ]),
            ('Фасовка', [
                ('Фасовка в мешки', 60, None),
            ]),
        ],
    },
    {
        'words': ('молоко',),
        'products': ('Молоко фермерское', 'Кефир 3,2 %', 'Творог 9 %'),
        'components': ('Бутылка ПЭТ 1 л', 'Крышка'),
        'uom': 'l', 'qty': (300, 1200),
        'stages': [
            ('Доильный зал', [
                ('Доение', 120, 'Подготовка вымени — 60–90 секунд, первые струйки в отдельную кружку.'),
                ('Охлаждение до +4 °C', 60, None),
            ]),
            ('Лаборатория', [
                ('Проверка жирности и кислотности', 20, 'Жир 3,4–4,0 %, кислотность 16–18 °Т.'),
            ]),
            ('Цех переработки', [
                ('Пастеризация', 30, '+76 °C, выдержка 20 секунд.'),
                ('Розлив', 60, None),
            ]),
        ],
    },
    {
        'words': ('дом «',),
        'products': ('Дом «Сфера» · 14 м²', 'Дом «Аркада» · 27 м²', 'Дом «Эко-Купол» · 42 м²'),
        'components': ('Брус клеёный', 'Утеплитель', 'Фанера влагостойкая', 'Мембрана'),
        'uom': 'unit', 'qty': (1, 3),
        'stages': [
            ('Цех каркаса', [
                ('Раскрой на ЧПУ', 480, 'Файл раскроя — из проекта, номер версии на каждой детали.'),
                ('Сборка панелей', 960, None),
            ]),
            ('Участок отделки', [
                ('Утепление и мембрана', 480, None),
                ('Обшивка', 720, None),
            ]),
            ('Монтаж у заказчика', [
                ('Сборка на фундаменте', 1440, 'Перед сборкой — нивелир, перепад фундамента не больше 5 мм.'),
                ('Сдача по акту', 120, None),
            ]),
        ],
    },
    {
        'words': ('сено', 'комбикорм'),
        'products': ('Комбикорм', 'Сено в рулонах — Челябинск', 'Зерносмесь для птицы'),
        'components': ('Ячмень', 'Пшеница', 'Шрот подсолнечный', 'Премикс'),
        'uom': 'kg', 'qty': (1000, 8000),
        'stages': [
            ('Дробильный участок', [
                ('Дробление зерна', 60, None),
            ]),
            ('Смесительный участок', [
                ('Дозирование по рецепту', 30, 'Рецепт — по возрасту поголовья; премикс вводить последним.'),
                ('Смешивание', 20, None),
            ]),
            ('Гранулятор', [
                ('Гранулирование', 90, None),
                ('Охлаждение гранул', 30, None),
            ]),
            ('Фасовка', [
                ('Фасовка в мешки по 40 кг', 40, None),
            ]),
        ],
    },
    {
        'words': ('спецодежд',),
        'products': ('Комплект спецодежды и СИЗ', 'Костюм рабочий летний', 'Жилет сигнальный'),
        'components': ('Ткань смесовая', 'Световозвращающая лента', 'Фурнитура'),
        'uom': 'unit', 'qty': (50, 300),
        'stages': [
            ('Раскройный цех', [
                ('Настил и раскрой', 120, 'Раскладка лекал — по карте, долевая нить вдоль кромки.'),
            ]),
            ('Швейный цех', [
                ('Пошив', 480, None),
                ('Установка фурнитуры', 120, None),
            ]),
            ('ОТК и упаковка', [
                ('Контроль швов и размеров', 60, None),
                ('Упаковка комплектов', 60, None),
            ]),
        ],
    },
]

UOMS = {'kg': 'uom.product_uom_kgm', 't': 'uom.product_uom_ton', 'm3': 'uom.product_uom_cubic_meter',
        'l': 'uom.product_uom_litre', 'unit': 'uom.product_uom_unit'}


def _template(name):
    low = name.lower()
    for tpl in TEMPLATES:
        if any(word in low for word in tpl['words']):
            return tpl
    return None


def _uom(env, code):
    return env.ref(UOMS[code], raise_if_not_found=False) or env.ref('uom.product_uom_unit')


def _product(env, company, name, uom, rnd):
    Product = env['product.product'].sudo().with_company(company)
    product = Product.search([('name', '=', name), ('company_id', '=', company.id)], limit=1)
    if not product:
        product = Product.create({
            'name': name, 'company_id': company.id, 'type': 'consu',
            'uom_id': uom.id, 'list_price': rnd.randrange(80, 9000, 10),
        })
    return product


def _bom(env, company, tpl, product, number, rnd):
    Bom = env['mrp.bom'].sudo().with_company(company)
    bom = Bom.search([('product_tmpl_id', '=', product.product_tmpl_id.id),
                      ('company_id', '=', company.id)], limit=1)
    if bom:
        return bom, False
    Center = env['mrp.workcenter'].sudo().with_company(company)
    unit = env.ref('uom.product_uom_unit')
    lines = []
    for comp in rnd.sample(tpl['components'], k=min(len(tpl['components']), rnd.randint(2, 4))):
        part = _product(env, company, comp, unit, rnd)
        lines.append((0, 0, {'product_id': part.id,
                              'product_qty': max(1, sum(tpl['qty']) // 2 * rnd.randint(2, 30) // 100)}))
    ops = []
    sequence = 0
    for stage, operations in tpl['stages']:
        center = Center.search([('name', '=', stage), ('company_id', '=', company.id)], limit=1) \
            or Center.create({'name': stage, 'company_id': company.id})
        for name, minutes, instruction in operations:
            sequence += 1
            ops.append((0, 0, {
                'name': name, 'workcenter_id': center.id, 'sequence': sequence,
                # У изделий рядом время своё: ±20 % к шаблону.
                'time_cycle_manual': max(5, round(minutes * rnd.uniform(0.8, 1.2) / 5) * 5),
                'coop_instruction': '<p>%s</p>' % instruction if instruction else False,
            }))
    bom = Bom.create({
        'product_tmpl_id': product.product_tmpl_id.id, 'company_id': company.id,
        'uom_id': product.uom_id.id,
        # Время операций в шаблоне — на типовую партию, как в живых
        # техкартах; на штуку выходили бы недели работы участка.
        'code': 'ТК-%02d' % number, 'product_qty': sum(tpl['qty']) // 2,
        'bom_line_ids': lines, 'operation_ids': ops,
    })
    return bom, True


def _batches(env, company, bom, tpl, rnd, count, today):
    """Выпуски по спецификации: готовые, в работе, план, отменённые."""
    Production = env['mrp.production'].sudo().with_company(company)
    made = 0
    for index in range(count):
        name = 'ПВ-%s-%02d' % (bom.code.split('-')[-1], index + 1)
        if Production.search_count([('name', '=', name), ('company_id', '=', company.id)]):
            continue
        low, high = tpl['qty']
        qty = rnd.randint(low, high)
        # Последние — свежие и ещё в работе; старые — готовые, реже отменённые.
        back = (count - index) * rnd.randint(9, 25)
        start = today - timedelta(days=back, hours=rnd.randint(0, 9))
        roll = rnd.random()
        state = 'done' if index < count - 2 else rnd.choice(('done', 'progress', 'confirmed', 'draft'))
        if state == 'done' and roll < 0.12:
            state = 'cancel'
        with env.cr.savepoint():
            production = Production.create({
                'name': name, 'product_id': bom.product_tmpl_id.product_variant_id.id,
                'bom_id': bom.id, 'product_qty': qty, 'company_id': company.id,
                'date_start': start,
            })
            made += 1
            if state == 'draft':
                continue
            production.action_confirm()
            if state == 'cancel':
                production.action_cancel()
                continue
            if state == 'confirmed':
                continue
            workorders = production.workorder_ids.sorted(lambda w: (w.operation_id.sequence, w.id))
            moment = start
            plan = []
            finished = len(workorders) if state == 'done' else rnd.randint(1, max(1, len(workorders) - 1))
            for wo in workorders[:finished]:
                spent = wo.duration_expected * rnd.uniform(0.85, 1.3)
                plan.append((wo, moment, moment + timedelta(minutes=spent), spent))
                moment += timedelta(minutes=spent + rnd.randint(10, 240))
            if state == 'progress':
                production.qty_producing = qty
            for wo, _begin, _end, _spent in plan:
                wo.button_start()
                wo.button_finish()
            if state == 'done':
                production.qty_producing = qty
                production.with_context(skip_consumption=True, skip_backorder=True,
                                        mo_ids_to_backorder=[]).button_mark_done()
            # Время и даты — как шло на самом деле, а не секунды прогона.
            # Готовый выпуск движок править не даёт, поэтому — запросом,
            # и только после записи накопленного движком: иначе он
            # досохраняет «сейчас» поверх.
            env.flush_all()
            cr = env.cr
            for wo, begin, end, _spent in plan:
                cr.execute('UPDATE mrp_workcenter_productivity SET date_start = %s, date_end = %s '
                           'WHERE workorder_id = %s', (begin, end, wo.id))
                cr.execute('UPDATE mrp_workorder SET date_start = %s, date_finished = %s '
                           'WHERE id = %s', (begin, end, wo.id))
            cr.execute('UPDATE mrp_production SET date_start = %s, date_finished = %s WHERE id = %s',
                       (start, moment if state == 'done' else None, production.id))
            production.invalidate_recordset()
            production.workorder_ids.invalidate_recordset()
    return made


def repair_dates(env):
    """Даты выпусков и операций — по журналу времени участков.

    Первый прогон на стенде записал даты до того, как движок досохранил
    свои, и у готовых партий осталось «сегодня». Журнал времени остался
    верным — из него даты и берутся. Трогает только демо-выпуски («ПВ-»).
    """
    env.flush_all()
    cr = env.cr
    # Пуск и завершение операции движок пишет двумя строками журнала, а
    # даты прогона у них одни и те же — после переноса дат вторая лишь
    # удваивала время. Остаётся одна строка на операцию.
    cr.execute("""
        DELETE FROM mrp_workcenter_productivity t
         USING mrp_workorder w, mrp_production p
         WHERE w.id = t.workorder_id AND p.id = w.production_id AND p.name LIKE 'ПВ-%%'
           AND t.id > (SELECT min(id) FROM mrp_workcenter_productivity
                        WHERE workorder_id = t.workorder_id)
    """)
    # Сколько заняло — тоже из журнала: длительность движок посчитал по
    # секундам прогона, и «заняло» всюду совпадало с «по плану».
    cr.execute("""
        UPDATE mrp_workcenter_productivity t
           SET duration = round(extract(epoch FROM (t.date_end - t.date_start)) / 60.0, 2)
          FROM mrp_workorder w, mrp_production p
         WHERE w.id = t.workorder_id AND p.id = w.production_id AND p.name LIKE 'ПВ-%%'
           AND t.date_end IS NOT NULL
           AND t.duration IS DISTINCT FROM round(extract(epoch FROM (t.date_end - t.date_start)) / 60.0, 2)
    """)
    cr.execute("""
        UPDATE mrp_workorder w SET duration = t.spent
          FROM (SELECT workorder_id, sum(duration) spent FROM mrp_workcenter_productivity
                 GROUP BY workorder_id) t, mrp_production p
         WHERE t.workorder_id = w.id AND p.id = w.production_id AND p.name LIKE 'ПВ-%%'
           AND w.duration IS DISTINCT FROM t.spent
    """)
    cr.execute("""
        UPDATE mrp_workorder w SET date_start = t.started, date_finished = t.ended
          FROM (SELECT workorder_id, min(date_start) started, max(date_end) ended
                  FROM mrp_workcenter_productivity GROUP BY workorder_id) t,
               mrp_production p
         WHERE t.workorder_id = w.id AND p.id = w.production_id AND p.name LIKE 'ПВ-%%'
           AND (w.date_start IS DISTINCT FROM t.started OR w.date_finished IS DISTINCT FROM t.ended)
    """)
    cr.execute("""
        UPDATE mrp_production p
           SET date_start = t.started,
               date_finished = CASE WHEN p.state = 'done' THEN t.ended ELSE p.date_finished END
          FROM (SELECT production_id, min(date_start) started, max(date_finished) ended
                  FROM mrp_workorder WHERE date_start IS NOT NULL GROUP BY production_id) t
         WHERE t.production_id = p.id AND p.name LIKE 'ПВ-%%' AND p.state IN ('done', 'progress')
           AND (p.date_start IS DISTINCT FROM t.started
                OR (p.state = 'done' AND p.date_finished IS DISTINCT FROM t.ended))
    """)
    env.invalidate_all()


def load_mrp(env, login='dashkevich'):
    if 'mrp.bom' not in env or 'bom_id' not in env['coop.resource']._fields:
        # Молча выходить нельзя: 27.10.2026 на боевой так и вышло — данные
        # coop_demo грузились раньше полей coop_mrp, и демо не появилось.
        _logger.warning('Производство: coop_mrp не загружен, демо пропущено')
        return 0
    Resource = env['coop.resource'].sudo()
    resources = Resource.with_context(active_test=False).search([
        ('listing_type', '=', 'offer'), ('resource_type', '=', 'material'),
        ('owner_id.is_company', '=', True), ('owner_id.coop_company_id', '!=', False),
    ], order='id')
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    showcase_orgs = env['coop.membership'].sudo().search([
        ('partner_id', '=', showcase.partner_id.id), ('state', '=', 'active'),
        ('power_ids.code', '=', 'sign')]).organization_id if showcase else env['res.partner']
    today = datetime.now().replace(minute=0, second=0, microsecond=0)
    boms = batches = linked = 0
    for resource in resources:
        tpl = _template(resource.name)
        if not tpl:
            continue
        org = resource.owner_id
        company = org.coop_company_id
        rnd = random.Random(20261027 + resource.id)
        if not org.coop_app_mrp:
            org.coop_app_mrp = True
        uom = _uom(env, tpl['uom'])
        names = [resource.name] + [p for p in tpl['products'] if p != resource.name]
        names = names[:rnd.randint(2, len(names))]
        main = None
        for number, name in enumerate(names, start=1):
            product = _product(env, company, name, uom, rnd)
            bom, fresh = _bom(env, company, tpl, product, number, rnd)
            boms += fresh
            main = main or bom
            # Свой жребий у каждой спецификации: повторный прогон, где
            # спецификация уже есть, иначе тянул бы другие числа и
            # дозаводил партии при каждом обновлении.
            lot = random.Random(20261027 + bom.id)
            count = lot.randint(3, 7) if bom == main else lot.randint(0, 4)
            batches += _batches(env, company, bom, tpl, lot, count, today)
        if not resource.bom_id:
            resource.bom_id = main
            linked += 1
        # Показ — у трёх из четырёх; у организации витрины — всегда.
        if not org.coop_show_process and (org in showcase_orgs or rnd.random() < 0.75):
            org.coop_show_process = True
    repair_dates(env)
    _logger.info('Производство: спецификаций %s, выпусков %s, ресурсов связано %s',
                 boms, batches, linked)
    return boms

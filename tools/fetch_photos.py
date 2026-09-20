# -*- coding: utf-8 -*-
"""Добор снимков для демонстрационных каталогов.

Зачем. Правило подбора снимка одно на предмет — «цемент», «доска
обрезная», «склад», — а записей с этим предметом в каталогах платформы
сотня. Один файл на правило значит сто одинаковых карточек: владелец
15 сентября 2026 сказал прямо — «одни и те же картинки везде, сделай все
разные, не хватает если скачай».

Что делает. Для каждого предмета из `PHOTO_RULES` берёт снимки в
Openverse и складывает рядом с уже имеющимся: `wood-planks.jpg`,
`wood-planks-2.jpg`, `wood-planks-3.jpg`. Загрузчик демо-данных выбирает
из них по названию записи, поэтому один и тот же товар в разных городах
получает разные снимки, а один и тот же — всегда свой.

Откуда. Викисклад: ключа не требует, снимков много, и поиск в нём
предметный. Сначала пробовался Openverse с отбором по CC0 — оказалось,
что под свободной лицензией там в основном музейные оцифровки: под
запросом «cement bags» приходит чёрно-белый архивный снимок опалубки
тридцатых годов. Плюс он отдаёт 401 после десятка запросов без ключа.

Лицензии здесь не разбираются намеренно. Решение владельца 15 сентября
2026: «бери любые фото и любые лого, мы позже это всё удалим и будут
только реальные». Это наполнение для показа, а не содержимое платформы;
перед боевым запуском набор меняется на снимки самих участников.

Запуск (сеть нужна, в наполнение не входит):

    python tools/fetch_photos.py            — добрать до 12 на предмет
    python tools/fetch_photos.py --per 24   — до двадцати четырёх
    python tools/fetch_photos.py --only cement-bag,warehouse
    python tools/fetch_photos.py --dry      — только посчитать, не качать
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PHOTO_DIR = os.path.join(ROOT, 'coop_demo', 'static', 'img', 'resources')
API = 'https://commons.wikimedia.org/w/api.php'
AGENT = 'dao-cooptech-demo-photos/1.0 (+https://github.com/daocooptech)'

# Предмет → что искать. Ключ — имя файла без расширения, то самое, что
# стоит в правилах подбора; значение — запрос по-английски: свободных
# снимков с русскими подписями на порядок меньше, а предмет от языка
# запроса не меняется.
ЗАПРОСЫ = {
    'air-compressor': 'air compressor',
    'apiary-hives': 'beehive apiary',
    'apple-orchard': 'apple orchard',
    'bakery-bread': 'bread bakery',
    'beef-meat': 'beef meat',
    'berry-harvest': 'berry harvest',
    'bicycle-repair': 'bicycle repair',
    'brick-stack': 'bricks stack',
    'bridge-repair': 'construction site',
    'camping-tent': 'camping tent',
    'car-rental': 'car parking',
    'cargo-bike': 'cargo bicycle',
    'carrot': 'carrots',
    'cattle-barn': 'cattle barn',
    'cctv-camera': 'security camera',
    'cement-bag': 'cement bags',
    'central-market': 'farmers market',
    'cheese-making': 'cheese dairy production',
    'coding-class': 'classroom training',
    'cold-storage': 'cold storage warehouse',
    'concrete-mixer': 'concrete mixer',
    'concrete-truck': 'concrete truck',
    'craft-workshop': 'craft workshop',
    'diesel-generator': 'diesel generator',
    'drying-kiln': 'grain dryer',
    'excavator': 'excavator',
    'field-sprayer': 'field sprayer fertilizer',
    'finance-money': 'money banknotes',
    'garage-building': 'garage building',
    'goat-farm': 'goats farm',
    'grain-silo': 'grain silo',
    'greenhouse': 'greenhouse',
    'hay-bales': 'hay bales',
    'herb-drying': 'drying herbs',
    'honey-extraction': 'honey extraction',
    'house-amie': 'wooden house',
    'land-plot': 'farmland field',
    'laptop-desk': 'laptop desk',
    'log-splitter': 'log splitter firewood',
    'metal-roof': 'metal roofing',
    'milk-bottles': 'milk bottles',
    'milk-tank': 'milk tanker',
    'mineral-wool': 'insulation material',
    'mini-tractor': 'small tractor',
    'nursery-seedlings': 'seedlings nursery',
    'office-desk': 'office desk',
    'pelmeni-making': 'dumplings making',
    'plastic-recycling': 'plastic recycling',
    'playground': 'playground',
    'potato-crate': 'potatoes crate',
    'pottery-wheel': 'pottery wheel',
    'poultry-house': 'poultry chickens',
    'printer3d-arm': '3d printer',
    'programmer': 'programmer computer',
    'radio-set': 'radio transceiver',
    'rebar-steel': 'steel rebar',
    'rotary-mower': 'mower',
    'scaffolding': 'scaffolding',
    'seed-drill': 'seed drill sowing',
    'server-rack': 'server rack',
    'sheep-flock': 'sheep flock',
    'timber-beam': 'timber beams',
    'tipping-trailer': 'truck trailer',
    'toolbox': 'tool box',
    'vegbox-csa': 'vegetable box',
    'walk-behind-tractor': 'two wheel tractor',
    'warehouse': 'warehouse building',
    'warehouse-shelves': 'warehouse shelves',
    'water-pump': 'water pump',
    'welding-machine': 'welding machine',
    'wood-planks': 'wooden planks',
    'workwear-ppe': 'work clothes safety',
}


# Дополнено 20 сентября 2026. Владелец: «в вакансиях нет картинок на
# нескольких позициях, а в потребностях у бетономешалки картинка
# моркови… сделай раз и навсегда всё качественно». Пересчёт по боевой
# базе показал 2102 записи без снимка, и 1375 из них — с названиями, под
# которые правила не было вовсе: крепёж, кабель, топливо, страхование,
# собрания, десятки профессий. Предметы взяты из этого пересчёта, а не
# придуманы.
ЗАПРОСЫ.update({
    # Материалы и расходники
    'fasteners': 'screws bolts nuts',
    'cable-coil': 'cable drum electric',
    'electrical-supplies': 'electrical installation material',
    'spare-parts': 'spare parts shelf',
    'sugar-sacks': 'sugar sack',
    'fuel-cans': 'jerrycan petrol fuel',
    'glass-jars': 'glass jars preserving',
    'plastic-crates': 'plastic crates',
    'sheet-metal': 'sheet metal stack',
    'clay-lump': 'potter working clay',
    'yarn-threads': 'yarn spools',
    'first-aid': 'first aid bandage medical supplies',
    'beehive-frames': 'beehive frames',
    # Энергия и сети
    'solar-panels': 'solar panels roof',
    'battery-inverter': 'battery energy storage',
    'ev-charger': 'electric car charging station',
    'power-meter': 'electricity meter',
    'network-switch': 'network switch rack',
    # Помещения и оснастка
    'sectional-gate': 'sectional overhead door',
    'library-shelves': 'library reading room',
    'office-furniture': 'office room chairs tables',
    'rubber-surface': 'rubber playground surface',
    'modular-building': 'modular container building',
    'ventilation-duct': 'ventilation duct industrial',
    'drip-irrigation': 'drip irrigation',
    'fish-pond': 'fish farm pond',
    'climbing-wall': 'climbing wall gym',
    # Станки и техника
    'woodworking-machine': 'woodworking machine workshop',
    'loom': 'weaving loom',
    'sewing-machine': 'industrial sewing machine',
    'dough-mixer': 'dough mixer bakery',
    'proofing-cabinet': 'bakery proofing cabinet',
    'deck-oven': 'bakery deck oven',
    'flour-mill-machine': 'flour milling machine grain',
    'washing-line': 'vegetable washing machine',
    'sorting-line': 'waste sorting conveyor',
    'baling-press': 'baling press waste',
    'lab-equipment': 'laboratory testing equipment',
    'mobile-crane': 'mobile crane truck',
    'van-delivery': 'delivery van',
    'camera-rig': 'video camera tripod',
    'cnc-machine': 'cnc lathe metalworking workshop',
    'printing-press': 'printing press machine',
    'blacksmith-forge': 'blacksmith anvil hammer',
    # Бумаги и услуги
    'documents-stamp': 'official documents stamp',
    'bank-office': 'bank office counter',
    'law-books': 'law books',
    'site-supervisor': 'construction site engineer',
    # Собрания и события
    'assembly-hall': 'conference hall audience seats',
    'community-gathering': 'community meeting people',
    'harvest-festival': 'harvest festival',
    'workshop-class': 'workshop class learning',
    'folk-dance': 'folk dance',
    'seed-swap': 'seeds exchange',
    'volunteer-cleanup': 'volunteers cleanup',
    'video-call': 'video conference',
    # Люди за делом
    'shop-counter': 'shop counter seller',
    'security-guard': 'security guard',
    'translator-desk': 'dictionary translation',
    'nurse': 'nurse patient care',
    'massage': 'massage back therapist',
    'ui-design': 'user interface design',
    'data-analytics': 'dashboard charts monitor',
    'editing-desk': 'editor proofreading',
    'code-review': 'software developer computer screen',
    'confectioner': 'pastry chef cake',
    'stone-restoration': 'stone mason restoration',
    'factory-operator': 'factory worker machine',
    'call-center': 'call center headset',
    'beekeeper-work': 'beekeeper hive',
    'electrician-work': 'electrician wiring',
    'vegetable-field': 'vegetable field harvest',
    # Нематериальное: знак, сорт, чертёж, методика
    'brand-design': 'logo design sketch',
    'blueprint': 'technical drawing',
    'wheat-field': 'wheat field',
    'coffee-roasting': 'coffee roasting',
})


def уже_есть(основа):
    """Сколько снимков этого предмета уже лежит."""
    счёт = 0
    if os.path.exists(os.path.join(PHOTO_DIR, основа + '.jpg')):
        счёт = 1
    n = 2
    while os.path.exists(os.path.join(PHOTO_DIR, '%s-%s.jpg' % (основа, n))):
        счёт += 1
        n += 1
    return счёт


# Чего на карточке каталога быть не должно, как бы точно оно ни
# отвечало запросу. Викисклад — это ещё и музей: под «cement bags»
# приходит рекламный плакат тридцатых годов, под «carrots» — гравюра из
# ботанического атласа. Владелец: «главное чтобы смотрелось максимально
# реально». Отсекаем по названию файла: у Викисклада оно говорящее.
НЕ_ФОТО = (
    'poster', 'advert', 'drawing', 'engraving', 'illustration', 'map',
    'diagram', 'logo', 'label', 'sign ', 'signboard', 'print', 'painting',
    'card', 'cover', 'plate', 'sketch', 'etching', 'lithograph', 'stamp',
    'patent', 'chart', 'graph', 'icon', 'coat of arms', 'seal', 'emblem',
    'banknote', 'postcard', 'cartoon', 'comic', 'book', 'page', 'manuscript',
    'титул', 'плакат',
    # Дополнено 20 сентября 2026 по просмотру трёхсот скачанных
    # снимков: под «cheese making» пришли чертежи сыроварни и
    # микрофотографии плесени, под «pottery clay» — музейные
    # горшки, под «first aid kit» — фотографии шведского дуэта с
    # таким названием.
    'museum', 'archaeolog', 'artifact', 'micrograph', 'microscope',
    'blueprint', 'schematic', 'technical drawing', 'render',
    'model of', 'scale model', 'mockup', 'exhibit', 'collection of',
    # По запросу «programmer computer» пришло изображение обнажённой
    # натуры — и прошло все проверки, потому что цветное и крупное.
    # Просмотр глазами это поймал, но полагаться на него нельзя.
    'nude', 'naked', 'erotic', 'topless', 'body paint', 'bodypaint',
    'lingerie', 'bikini', 'corpse', 'slaughter', 'carcass', 'butcher',
)


def спросить(запрос, сколько):
    """Адреса снимков по предмету.

    Берутся уменьшённые до 640 точек, а не исходники: в каталоге снимок
    показывается карточкой, а полноразмерные сканы Викисклада весят по
    несколько мегабайт и раздули бы хранилище на порядок.
    """
    параметры = urllib.parse.urlencode({
        'action': 'query',
        'generator': 'search',
        'gsrsearch': 'filetype:bitmap %s' % запрос,
        'gsrnamespace': '6',
        'gsrlimit': str(min(max(сколько * 3, 10), 50)),
        'prop': 'imageinfo',
        'iiprop': 'url|size',
        'iiurlwidth': '640',
        'format': 'json',
    })
    запрос_http = urllib.request.Request(API + '?' + параметры,
                                         headers={'User-Agent': AGENT})
    with urllib.request.urlopen(запрос_http, timeout=30) as ответ:
        данные = json.load(ответ)
    страницы = (данные.get('query') or {}).get('pages') or {}
    # Поиск по Викискладу отвечает широко: под «cement bags» приходит
    # улица, на краю которой лежат мешки. Отбираем по названию файла —
    # оно у Викисклада осмысленное и содержит предмет съёмки. Владелец
    # сказал про картинки прямо: «что бы совпадали с названием».
    слова = [с for с in re.split(r'\W+', запрос.lower()) if len(с) > 3]
    адреса = []
    for стр in страницы.values():
        сведения = (стр.get('imageinfo') or [{}])[0]
        адрес = сведения.get('thumburl') or сведения.get('url')
        название = (стр.get('title') or '').lower()
        if not адрес or not re.search(r'\.(jpg|jpeg|png)(\?|$)', адрес, re.I):
            continue
        if слова and not any(с in название for с in слова):
            continue
        if any(с in название for с in НЕ_ФОТО):
            continue
        адреса.append(адрес)
    return адреса


def годится(путь):
    """Похож ли файл на снимок предмета, а не на что попало.

    Свободные хранилища — это во многом музейные оцифровки: под запросом
    «cement bags» приходит чёрно-белый архивный снимок опалубки 1930-х
    годов. В каталоге кооператива он читается как ошибка, и владелец
    сказал прямо: картинка должна совпадать с названием.

    Разобрать содержимое снимка здесь нечем, но отсеять заведомо
    негодное можно по трём признакам, и они снимают почти весь мусор:

    * мелкий — значок, заглушка или миниатюра;
    * вытянутый — разворот книги, схема, панорама;
    * обесцвеченный — архивная оцифровка.

    Порог цветности взят с запасом: снимок склада в пасмурный день тоже
    неярок, и рубить по нему нельзя.
    """
    try:
        from PIL import Image
    except ImportError:
        return True                                 # нет чем проверить — берём
    try:
        with Image.open(путь) as рисунок:
            ширина, высота = рисунок.size
            if min(ширина, высота) < 400:
                return False
            отношение = ширина / float(высота)
            if отношение < 0.5 or отношение > 2.2:
                return False
            малый = рисунок.convert('RGB').resize((64, 64))
            сумма = 0
            точки = list(малый.getdata())
            for r, g, b in точки:
                сумма += max(r, g, b) - min(r, g, b)
            насыщенность = сумма / float(len(точки))
            return насыщенность >= 18
    except Exception:
        return False


def скачать(адрес, путь):
    запрос_http = urllib.request.Request(адрес, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(запрос_http, timeout=60) as ответ:
        данные = ответ.read()
    # Слишком мелкое — это значок или заглушка, а не снимок предмета.
    if len(данные) < 8000:
        return False
    with open(путь, 'wb') as fh:
        fh.write(данные)
    if not годится(путь):
        os.remove(путь)
        return False
    return True


def main():
    разбор = argparse.ArgumentParser()
    разбор.add_argument('--per', type=int, default=12,
                        help='сколько снимков держать на предмет')
    разбор.add_argument('--only', default='',
                        help='через запятую: только эти предметы')
    разбор.add_argument('--dry', action='store_true',
                        help='посчитать, но не качать')
    аргументы = разбор.parse_args()

    только = {s.strip() for s in аргументы.only.split(',') if s.strip()}
    итог = {'добавлено': 0, 'хватало': 0, 'не нашлось': []}

    for основа, запрос in sorted(ЗАПРОСЫ.items()):
        if только and основа not in только:
            continue
        есть = уже_есть(основа)
        нужно = аргументы.per - есть
        if нужно <= 0:
            итог['хватало'] += 1
            continue
        if аргументы.dry:
            print('%-24s есть %-3s нужно ещё %s' % (основа, есть, нужно))
            continue
        try:
            адреса = спросить(запрос, нужно)
        except Exception as e:                      # сеть, а не наша логика
            print('%-24s не спросилось: %s' % (основа, e))
            continue
        добавлено = 0
        n = есть + 1 if есть else 1
        for адрес in адреса:
            if добавлено >= нужно:
                break
            имя = ('%s.jpg' % основа) if n == 1 else ('%s-%s.jpg' % (основа, n))
            путь = os.path.join(PHOTO_DIR, имя)
            if os.path.exists(путь):
                n += 1
                continue
            try:
                if скачать(адрес, путь):
                    добавлено += 1
                    n += 1
            except Exception:
                continue
            time.sleep(0.2)                         # не частить с чужим сервером
        итог['добавлено'] += добавлено
        if добавлено < нужно:
            итог['не нашлось'].append('%s (+%s из %s)' % (основа, добавлено, нужно))
        print('%-24s было %-3s добавлено %s' % (основа, есть, добавлено))

    if not аргументы.dry:
        print('\nвсего добавлено: %s' % итог['добавлено'])
        if итог['не нашлось']:
            print('свободных снимков не хватило: %s'
                  % ', '.join(итог['не нашлось']))
    return 0


if __name__ == '__main__':
    sys.exit(main())

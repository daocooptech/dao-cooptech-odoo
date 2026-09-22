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
REQUESTS = {
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
REQUESTS.update({
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


def already_there(base):
    """Сколько снимков этого предмета уже лежит."""
    account = 0
    if os.path.exists(os.path.join(PHOTO_DIR, base + '.jpg')):
        account = 1
    n = 2
    while os.path.exists(os.path.join(PHOTO_DIR, '%s-%s.jpg' % (base, n))):
        account += 1
        n += 1
    return account


# Чего на карточке каталога быть не должно, как бы точно оно ни
# отвечало запросу. Викисклад — это ещё и музей: под «cement bags»
# приходит рекламный плакат тридцатых годов, под «carrots» — гравюра из
# ботанического атласа. Владелец: «главное чтобы смотрелось максимально
# реально». Отсекаем по названию файла: у Викисклада оно говорящее.
NOT_PHOTO = (
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


def ask(request, how_many):
    """Адреса снимков по предмету.

    Берутся уменьшённые до 640 точек, а не исходники: в каталоге снимок
    показывается карточкой, а полноразмерные сканы Викисклада весят по
    несколько мегабайт и раздули бы хранилище на порядок.
    """
    params = urllib.parse.urlencode({
        'action': 'query',
        'generator': 'search',
        'gsrsearch': 'filetype:bitmap %s' % request,
        'gsrnamespace': '6',
        'gsrlimit': str(min(max(how_many * 3, 10), 50)),
        'prop': 'imageinfo',
        'iiprop': 'url|size',
        'iiurlwidth': '640',
        'format': 'json',
    })
    http_request = urllib.request.Request(API + '?' + params,
                                         headers={'User-Agent': AGENT})
    with urllib.request.urlopen(http_request, timeout=30) as answer:
        data = json.load(answer)
    pages = (data.get('query') or {}).get('pages') or {}
    # Поиск по Викискладу отвечает широко: под «cement bags» приходит
    # улица, на краю которой лежат мешки. Отбираем по названию файла —
    # оно у Викисклада осмысленное и содержит предмет съёмки. Владелец
    # сказал про картинки прямо: «что бы совпадали с названием».
    words = [ch for ch in re.split(r'\W+', request.lower()) if len(ch) > 3]
    addresses = []
    for page in pages.values():
        info = (page.get('imageinfo') or [{}])[0]
        address = info.get('thumburl') or info.get('url')
        title = (page.get('title') or '').lower()
        if not address or not re.search(r'\.(jpg|jpeg|png)(\?|$)', address, re.I):
            continue
        if words and not any(ch in title for ch in words):
            continue
        if any(ch in title for ch in NOT_PHOTO):
            continue
        addresses.append(address)
    return addresses


def fits(path):
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
        with Image.open(path) as image:
            width, height = image.size
            if min(width, height) < 400:
                return False
            ratio = width / float(height)
            if ratio < 0.5 or ratio > 2.2:
                return False
            small_one = image.convert('RGB').resize((64, 64))
            amount = 0
            points = list(small_one.getdata())
            for r, g, b in points:
                amount += max(r, g, b) - min(r, g, b)
            saturation = amount / float(len(points))
            return saturation >= 18
    except Exception:
        return False


def download(address, path):
    http_request = urllib.request.Request(address, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(http_request, timeout=60) as answer:
        data = answer.read()
    # Слишком мелкое — это значок или заглушка, а не снимок предмета.
    if len(data) < 8000:
        return False
    with open(path, 'wb') as fh:
        fh.write(data)
    if not fits(path):
        os.remove(path)
        return False
    return True


def main():
    parsed = argparse.ArgumentParser()
    parsed.add_argument('--per', type=int, default=12,
                        help='сколько снимков держать на предмет')
    parsed.add_argument('--only', default='',
                        help='через запятую: только эти предметы')
    parsed.add_argument('--dry', action='store_true',
                        help='посчитать, но не качать')
    args = parsed.parse_args()

    only = {s.strip() for s in args.only.split(',') if s.strip()}
    total = {'добавлено': 0, 'хватало': 0, 'не нашлось': []}

    for base, request in sorted(REQUESTS.items()):
        if only and base not in only:
            continue
        exists = already_there(base)
        needed = args.per - exists
        if needed <= 0:
            total['хватало'] += 1
            continue
        if args.dry:
            print('%-24s есть %-3s нужно ещё %s' % (base, exists, needed))
            continue
        try:
            addresses = ask(request, needed)
        except Exception as e:                      # сеть, а не наша логика
            print('%-24s не спросилось: %s' % (base, e))
            continue
        added = 0
        n = exists + 1 if exists else 1
        for address in addresses:
            if added >= needed:
                break
            name = ('%s.jpg' % base) if n == 1 else ('%s-%s.jpg' % (base, n))
            path = os.path.join(PHOTO_DIR, name)
            if os.path.exists(path):
                n += 1
                continue
            try:
                if download(address, path):
                    added += 1
                    n += 1
            except Exception:
                continue
            time.sleep(0.2)                         # не частить с чужим сервером
        total['добавлено'] += added
        if added < needed:
            total['не нашлось'].append('%s (+%s из %s)' % (base, added, needed))
        print('%-24s было %-3s добавлено %s' % (base, exists, added))

    if not args.dry:
        print('\nвсего добавлено: %s' % total['добавлено'])
        if total['не нашлось']:
            print('свободных снимков не хватило: %s'
                  % ', '.join(total['не нашлось']))
    return 0


if __name__ == '__main__':
    sys.exit(main())

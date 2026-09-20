# -*- coding: utf-8 -*-
"""Добор эмблем для организаций демонстрационного наполнения.

Зачем. Организаций в наполнении под две сотни, а свободных эмблем в
наборе было 98 — остальным доставался нарисованный знак-буква. Владелец
16 сентября 2026, увидев такие плитки: «у организаций какие то иконки
вместо логотипов… найти и скачать настоящие логотипы и проверь что бы
было у всех».

Про лицензии. Берутся только общественное достояние и CC0, и лицензия
проверяется у каждого файла, а не предполагается по категории: в
Викискладе рядом с общественным достоянием лежат файлы с условиями
указания авторства и с запретом изменений.

Про смысл. Организации наполнения выдуманные, и знак настоящего
предприятия на выдуманной записи остаётся чужим знаком. Владелец об этом
предупреждён и выбрал этот путь; решение о наполнении от 15 сентября
2026 — «бери любые фото и любые лого, мы позже это всё удалим и будут
только реальные».

Запуск (нужна сеть, в наполнение не входит):

    python tools/fetch_marks.py             — добрать набор до 220
    python tools/fetch_marks.py --target 300
    python tools/fetch_marks.py --dry       — только посчитать
"""
import argparse
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MARKS = os.path.join(ROOT, 'coop_demo', 'static', 'img', 'marks')
MANIFEST = os.path.join(MARKS, 'MANIFEST.json')
API = 'https://commons.wikimedia.org/w/api.php'
AGENT = 'dao-cooptech-demo/1.0 (emblems for demo catalogue)'

# Запросы подобраны так, чтобы приходили знаки предприятий и обществ, а
# не гербы городов и не значки приложений: и то и другое в каталоге
# кооперативов читается как ошибка.
ЗАПРОСЫ = [
    'logo cooperative',
    'logo artel',
    'emblem factory soviet',
    'logo kolkhoz',
    'trademark soviet enterprise',
    'logo workers union',
    'emblem machinery plant',
    'logo dairy plant',
    'logo bakery',
    'logo textile mill',
    'emblem shipyard',
    'logo construction trust',
    'logo agricultural society',
    'emblem credit union',
    'logo consumer society',
    'logo mining company historical',
    'emblem railway society',
    'logo brewery historical',
]

СВОБОДНЫЕ = ('public domain', 'cc0', 'pd-')

НЕ_ЗНАК = ('coat of arms', 'flag of', 'seal of', 'map of', 'screenshot',
           'icon set', 'diagram', 'chart', 'portrait', 'photograph')



# Отвергнутые при просмотре: знаки известных марок, обрывки документов и
# фотографии, которые поиск приносит снова и снова. Без этого списка
# следующий добор скачивает их заново — манифест-то их уже не помнит.
# Владелец 20 сентября 2026: «максимальная приближенность к реальности».
# Кроссовки и кондиционеры к кооперативу отношения не имеют.
НЕ_БРАТЬ = (
    'adidas', 'daikin', 'fischer', 'fivethirtyeight', 'nabisco', 'amfam',
    'pforzheim', 'tokyo-university', 'phi-rho-sigma', 'dror-habonim',
    'international-fur', 'pr-t-pour-le-travail', 'yauza-209',
    'european-sleeper', 'badge-of-mackenzie', 'plan-de-recuperac', '5-lei',
    'a-desk-book',
)


def манифест():
    if not os.path.exists(MANIFEST):
        return []
    with open(MANIFEST, encoding='utf-8') as fh:
        return json.load(fh)


def значение(мета, ключ):
    значение_поля = мета.get(ключ, {}).get('value')
    if not isinstance(значение_поля, str):
        return ''
    return re.sub('<[^>]+>', '', значение_поля).strip()


def спросить(запрос, сколько):
    """Знаки по запросу вместе с лицензией каждого файла.

    Лицензия спрашивается тем же запросом, а не отдельным походом на
    каждый файл: их тут сотни, и второй запрос на каждый удвоил бы время
    и нагрузку на чужой сервер.
    """
    параметры = urllib.parse.urlencode({
        'action': 'query',
        'generator': 'search',
        'gsrsearch': 'filetype:bitmap %s' % запрос,
        'gsrnamespace': '6',
        'gsrlimit': str(min(max(сколько * 3, 20), 50)),
        'prop': 'imageinfo',
        'iiprop': 'url|size|extmetadata',
        'iiurlwidth': '512',
        'format': 'json',
    })
    запрос_http = urllib.request.Request(API + '?' + параметры,
                                         headers={'User-Agent': AGENT})
    with urllib.request.urlopen(запрос_http, timeout=30) as ответ:
        данные = json.load(ответ)
    страницы = (данные.get('query') or {}).get('pages') or {}
    найденное = []
    for стр in страницы.values():
        сведения = (стр.get('imageinfo') or [{}])[0]
        адрес = сведения.get('thumburl') or сведения.get('url')
        название = стр.get('title') or ''
        мета = сведения.get('extmetadata') or {}
        лицензия = (значение(мета, 'LicenseShortName')
                    or значение(мета, 'License'))
        if not адрес or not re.search(r'\.(png|jpg|jpeg)(\?|$)', адрес, re.I):
            continue
        if not any(с in лицензия.lower() for с in СВОБОДНЫЕ):
            continue
        if any(с in название.lower() for с in НЕ_ЗНАК):
            continue
        найденное.append({
            'title': название[5:] if название.startswith('File:') else название,
            'url': адрес,
            'license': лицензия,
            'author': значение(мета, 'Artist')[:120] or 'Unknown author',
            'source': 'https://commons.wikimedia.org/wiki/%s'
                      % urllib.parse.quote(название.replace(' ', '_')),
        })
    return найденное


# Категории Викисклада, где лежат заводские знаки — те самые монограммы,
# которые в каталоге читаются как эмблема предприятия. Поиск словами
# такого не находит: у этих файлов в названии стоит имя завода, а не
# слово «logo». Добавлено 20 сентября 2026, когда в наборе оказалось
# семьдесят восемь фотографий вместо знаков — спутниковые снимки,
# развороты удостоверений, портреты.
КАТЕГОРИИ = [
    'Category:Factory logos of Soviet electronics industry',
    'Category:Factory logos of Soviet integrated circuits',
    'Category:Factory logos of Soviet vacuum tubes',
    'Category:Logos of the Soviet Union',
    'Category:Logos of organizations of the Soviet Union',
    'Category:Logos of cooperatives',
    'Category:Monograms',
    'Category:Black triangular logos',
]


def из_категории(категория, сколько):
    """Знаки из категории Викисклада — вместе с лицензией каждого."""
    параметры = urllib.parse.urlencode({
        'action': 'query',
        'generator': 'categorymembers',
        'gcmtitle': категория,
        'gcmtype': 'file',
        'gcmlimit': str(min(max(сколько * 2, 20), 200)),
        'prop': 'imageinfo',
        'iiprop': 'url|size|extmetadata',
        'iiurlwidth': '512',
        'format': 'json',
    })
    запрос_http = urllib.request.Request(API + '?' + параметры,
                                         headers={'User-Agent': AGENT})
    with urllib.request.urlopen(запрос_http, timeout=30) as ответ:
        данные = json.load(ответ)
    страницы = (данные.get('query') or {}).get('pages') or {}
    найденное = []
    for стр in страницы.values():
        сведения = (стр.get('imageinfo') or [{}])[0]
        адрес = сведения.get('thumburl') or сведения.get('url')
        название = стр.get('title') or ''
        мета = сведения.get('extmetadata') or {}
        лицензия = (значение(мета, 'LicenseShortName')
                    or значение(мета, 'License'))
        if not адрес or not re.search(r'\.(png|jpg|jpeg)(\?|$)', адрес, re.I):
            continue
        if not any(с in лицензия.lower() for с in СВОБОДНЫЕ):
            continue
        if any(с in название.lower() for с in НЕ_ЗНАК):
            continue
        найденное.append({
            'title': название[5:] if название.startswith('File:') else название,
            'url': адрес,
            'license': лицензия,
            'author': значение(мета, 'Artist')[:120] or 'Unknown author',
            'source': 'https://commons.wikimedia.org/wiki/%s'
                      % urllib.parse.quote(название.replace(' ', '_')),
        })
    return найденное


def плоский(путь):
    """Знак это или фотография.

    Знак нарисован: в нём считанные цвета и большое одноцветное поле.
    Фотография — сотни оттенков. Порог в сорок квантованных цветов
    отделяет одно от другого на всём наборе: монограммы укладываются в
    десяток, спутниковый снимок даёт за сотню.
    """
    try:
        from PIL import Image
    except ImportError:
        return True
    try:
        with Image.open(путь) as рисунок:
            маленький = рисунок.convert('RGB').resize((64, 64))
            цвета = {}
            for r, g, b in list(маленький.getdata()):
                ключ = (r // 32, g // 32, b // 32)
                цвета[ключ] = цвета.get(ключ, 0) + 1
            return len(цвета) < 40
    except Exception:
        return False


def отвергнут(имя):
    """Знак из списка отвергнутых — не берём его и при следующем доборе."""
    return any(с in имя for с in НЕ_БРАТЬ)


def имя_файла(название):
    основа = re.sub(r'[^a-z0-9]+', '-', название.lower()).strip('-')
    основа = re.sub(r'-(png|jpg|jpeg|svg)$', '', основа)
    return (основа or 'mark')[:60] + '.png'


def скачать(адрес, путь):
    запрос_http = urllib.request.Request(адрес, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(запрос_http, timeout=60) as ответ:
        данные = ответ.read()
    # Мельче трёх килобайт — это заглушка, а не знак.
    if len(данные) < 3000:
        return False
    with open(путь, 'wb') as fh:
        fh.write(данные)
    if not плоский(путь):
        os.remove(путь)
        return False
    return True


def main():
    разбор = argparse.ArgumentParser()
    разбор.add_argument('--target', type=int, default=220,
                        help='сколько знаков должно быть в наборе')
    разбор.add_argument('--dry', action='store_true')
    аргументы = разбор.parse_args()

    записи = манифест()
    было = len(записи)
    имена = {з.get('file') for з in записи}
    нужно = аргументы.target - было
    print('в наборе %s, нужно добрать %s' % (было, max(нужно, 0)))
    if нужно <= 0 or аргументы.dry:
        return

    добавлено = 0
    for категория in КАТЕГОРИИ:
        if добавлено >= нужно:
            break
        try:
            найденное = из_категории(категория, нужно - добавлено)
        except Exception as ошибка:
            print('  %s: не спросилось — %s' % (категория, ошибка))
            continue
        взято = 0
        for знак in найденное:
            if добавлено >= нужно:
                break
            имя = имя_файла(знак['title'])
            if имя in имена or отвергнут(имя):
                continue
            путь = os.path.join(MARKS, имя)
            try:
                if not скачать(знак['url'], путь):
                    continue
            except Exception:
                continue
            имена.add(имя)
            записи.append({
                'file': имя,
                'title': знак['title'],
                'license': знак['license'],
                'source': знак['source'],
                'author': знак['author'],
            })
            добавлено += 1
            взято += 1
        print('  %s: взято %s' % (категория, взято))

    for запрос in ЗАПРОСЫ:
        if добавлено >= нужно:
            break
        try:
            найденное = спросить(запрос, нужно - добавлено)
        except Exception as ошибка:
            print('  %s: не спросилось — %s' % (запрос, ошибка))
            continue
        взято = 0
        for знак in найденное:
            if добавлено >= нужно:
                break
            имя = имя_файла(знак['title'])
            if имя in имена or отвергнут(имя):
                continue
            путь = os.path.join(MARKS, имя)
            try:
                if not скачать(знак['url'], путь):
                    continue
            except Exception:
                continue
            имена.add(имя)
            записи.append({
                'file': имя,
                'title': знак['title'],
                'license': знак['license'],
                'source': знак['source'],
                'author': знак['author'],
            })
            добавлено += 1
            взято += 1
        print('  %s: взято %s' % (запрос, взято))

    with open(MANIFEST, 'w', encoding='utf-8') as fh:
        json.dump(записи, fh, ensure_ascii=False, indent=2)
    print('стало %s знаков (+%s)' % (len(записи), добавлено))


if __name__ == '__main__':
    main()

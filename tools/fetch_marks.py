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
REQUESTS = [
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

FREE = ('public domain', 'cc0', 'pd-')

NOT_MARK = ('coat of arms', 'flag of', 'seal of', 'map of', 'screenshot',
           'icon set', 'diagram', 'chart', 'portrait', 'photograph')



# Отвергнутые при просмотре: знаки известных марок, обрывки документов и
# фотографии, которые поиск приносит снова и снова. Без этого списка
# следующий добор скачивает их заново — манифест-то их уже не помнит.
# Владелец 20 сентября 2026: «максимальная приближенность к реальности».
# Кроссовки и кондиционеры к кооперативу отношения не имеют.
SKIP = (
    'adidas', 'daikin', 'fischer', 'fivethirtyeight', 'nabisco', 'amfam',
    'pforzheim', 'tokyo-university', 'phi-rho-sigma', 'dror-habonim',
    'international-fur', 'pr-t-pour-le-travail', 'yauza-209',
    'european-sleeper', 'badge-of-mackenzie', 'plan-de-recuperac', '5-lei',
    'a-desk-book',
)


def manifest():
    if not os.path.exists(MANIFEST):
        return []
    with open(MANIFEST, encoding='utf-8') as fh:
        return json.load(fh)


def value(meta, key):
    field_value = meta.get(key, {}).get('value')
    if not isinstance(field_value, str):
        return ''
    return re.sub('<[^>]+>', '', field_value).strip()


def ask(request, how_many):
    """Знаки по запросу вместе с лицензией каждого файла.

    Лицензия спрашивается тем же запросом, а не отдельным походом на
    каждый файл: их тут сотни, и второй запрос на каждый удвоил бы время
    и нагрузку на чужой сервер.
    """
    params = urllib.parse.urlencode({
        'action': 'query',
        'generator': 'search',
        'gsrsearch': 'filetype:bitmap %s' % request,
        'gsrnamespace': '6',
        'gsrlimit': str(min(max(how_many * 3, 20), 50)),
        'prop': 'imageinfo',
        'iiprop': 'url|size|extmetadata',
        'iiurlwidth': '512',
        'format': 'json',
    })
    http_request = urllib.request.Request(API + '?' + params,
                                         headers={'User-Agent': AGENT})
    with urllib.request.urlopen(http_request, timeout=30) as answer:
        data = json.load(answer)
    pages = (data.get('query') or {}).get('pages') or {}
    found_one = []
    for page in pages.values():
        info = (page.get('imageinfo') or [{}])[0]
        address = info.get('thumburl') or info.get('url')
        title = page.get('title') or ''
        meta = info.get('extmetadata') or {}
        license = (value(meta, 'LicenseShortName')
                    or value(meta, 'License'))
        if not address or not re.search(r'\.(png|jpg|jpeg)(\?|$)', address, re.I):
            continue
        if not any(ch in license.lower() for ch in FREE):
            continue
        if any(ch in title.lower() for ch in NOT_MARK):
            continue
        found_one.append({
            'title': title[5:] if title.startswith('File:') else title,
            'url': address,
            'license': license,
            'author': value(meta, 'Artist')[:120] or 'Unknown author',
            'source': 'https://commons.wikimedia.org/wiki/%s'
                      % urllib.parse.quote(title.replace(' ', '_')),
        })
    return found_one


# Категории Викисклада, где лежат заводские знаки — те самые монограммы,
# которые в каталоге читаются как эмблема предприятия. Поиск словами
# такого не находит: у этих файлов в названии стоит имя завода, а не
# слово «logo». Добавлено 20 сентября 2026, когда в наборе оказалось
# семьдесят восемь фотографий вместо знаков — спутниковые снимки,
# развороты удостоверений, портреты.
CATEGORIES = [
    'Category:Factory logos of Soviet electronics industry',
    'Category:Factory logos of Soviet integrated circuits',
    'Category:Factory logos of Soviet vacuum tubes',
    'Category:Logos of the Soviet Union',
    'Category:Logos of organizations of the Soviet Union',
    'Category:Logos of cooperatives',
    'Category:Monograms',
    'Category:Black triangular logos',
]


def from_category(category, how_many):
    """Знаки из категории Викисклада — вместе с лицензией каждого."""
    params = urllib.parse.urlencode({
        'action': 'query',
        'generator': 'categorymembers',
        'gcmtitle': category,
        'gcmtype': 'file',
        'gcmlimit': str(min(max(how_many * 2, 20), 200)),
        'prop': 'imageinfo',
        'iiprop': 'url|size|extmetadata',
        'iiurlwidth': '512',
        'format': 'json',
    })
    http_request = urllib.request.Request(API + '?' + params,
                                         headers={'User-Agent': AGENT})
    with urllib.request.urlopen(http_request, timeout=30) as answer:
        data = json.load(answer)
    pages = (data.get('query') or {}).get('pages') or {}
    found_one = []
    for page in pages.values():
        info = (page.get('imageinfo') or [{}])[0]
        address = info.get('thumburl') or info.get('url')
        title = page.get('title') or ''
        meta = info.get('extmetadata') or {}
        license = (value(meta, 'LicenseShortName')
                    or value(meta, 'License'))
        if not address or not re.search(r'\.(png|jpg|jpeg)(\?|$)', address, re.I):
            continue
        if not any(ch in license.lower() for ch in FREE):
            continue
        if any(ch in title.lower() for ch in NOT_MARK):
            continue
        found_one.append({
            'title': title[5:] if title.startswith('File:') else title,
            'url': address,
            'license': license,
            'author': value(meta, 'Artist')[:120] or 'Unknown author',
            'source': 'https://commons.wikimedia.org/wiki/%s'
                      % urllib.parse.quote(title.replace(' ', '_')),
        })
    return found_one


def flat(path):
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
        with Image.open(path) as image:
            small = image.convert('RGB').resize((64, 64))
            colors = {}
            for r, g, b in list(small.getdata()):
                key = (r // 32, g // 32, b // 32)
                colors[key] = colors.get(key, 0) + 1
            return len(colors) < 40
    except Exception:
        return False


def rejected(name):
    """Знак из списка отвергнутых — не берём его и при следующем доборе."""
    return any(ch in name for ch in SKIP)


def file_name(title):
    base = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    base = re.sub(r'-(png|jpg|jpeg|svg)$', '', base)
    return (base or 'mark')[:60] + '.png'


def download(address, path):
    http_request = urllib.request.Request(address, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(http_request, timeout=60) as answer:
        data = answer.read()
    # Мельче трёх килобайт — это заглушка, а не знак.
    if len(data) < 3000:
        return False
    with open(path, 'wb') as fh:
        fh.write(data)
    if not flat(path):
        os.remove(path)
        return False
    return True


def main():
    parsed = argparse.ArgumentParser()
    parsed.add_argument('--target', type=int, default=220,
                        help='сколько знаков должно быть в наборе')
    parsed.add_argument('--dry', action='store_true')
    args = parsed.parse_args()

    records = manifest()
    was = len(records)
    names = {entry.get('file') for entry in records}
    needed = args.target - was
    print('в наборе %s, нужно добрать %s' % (was, max(needed, 0)))
    if needed <= 0 or args.dry:
        return

    added = 0
    for category in CATEGORIES:
        if added >= needed:
            break
        try:
            found_one = from_category(category, needed - added)
        except Exception as error:
            print('  %s: не спросилось — %s' % (category, error))
            continue
        taken_count = 0
        for mark in found_one:
            if added >= needed:
                break
            name = file_name(mark['title'])
            if name in names or rejected(name):
                continue
            path = os.path.join(MARKS, name)
            try:
                if not download(mark['url'], path):
                    continue
            except Exception:
                continue
            names.add(name)
            records.append({
                'file': name,
                'title': mark['title'],
                'license': mark['license'],
                'source': mark['source'],
                'author': mark['author'],
            })
            added += 1
            taken_count += 1
        print('  %s: взято %s' % (category, taken_count))

    for request in REQUESTS:
        if added >= needed:
            break
        try:
            found_one = ask(request, needed - added)
        except Exception as error:
            print('  %s: не спросилось — %s' % (request, error))
            continue
        taken_count = 0
        for mark in found_one:
            if added >= needed:
                break
            name = file_name(mark['title'])
            if name in names or rejected(name):
                continue
            path = os.path.join(MARKS, name)
            try:
                if not download(mark['url'], path):
                    continue
            except Exception:
                continue
            names.add(name)
            records.append({
                'file': name,
                'title': mark['title'],
                'license': mark['license'],
                'source': mark['source'],
                'author': mark['author'],
            })
            added += 1
            taken_count += 1
        print('  %s: взято %s' % (request, taken_count))

    with open(MANIFEST, 'w', encoding='utf-8') as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
    print('стало %s знаков (+%s)' % (len(records), added))


if __name__ == '__main__':
    main()

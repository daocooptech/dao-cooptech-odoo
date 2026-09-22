# -*- coding: utf-8 -*-
"""Заменить один снимок, который не совпадает со своим названием.

Зачем отдельно от `fetch_photos.py`. Тот добирает набор: смотрит, чего
не хватает, и складывает рядом. А здесь обратная задача — файл есть, но
на нём не то: под именем `weaving-loom.jpg` лежал осенний лес, под
`bakery.jpg` — деревенский дом, под `cheese-making.jpg` — гравюра из
книги. Просмотр глазами это ловит, а дозагрузка — нет: для неё снимок
на месте.

Запуск (нужна сеть, в наполнение не входит):

    python tools/fetch_one.py skills/weaving-loom "weaving loom textile"
    python tools/fetch_one.py --list замена.txt

Файл списка: по строке на снимок, «папка/имя<TAB>запрос по-английски».
Старый файл не удаляется молча — он переписывается только после того,
как новый скачан и прошёл проверку.
"""
import argparse
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_photos                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, 'coop_demo', 'static', 'img')


def replace(target, request):
    """Скачать снимок по запросу и положить вместо `цель`."""
    path = os.path.join(IMG_DIR, target.replace('/', os.sep))
    if not path.lower().endswith(('.jpg', '.jpeg', '.png')):
        path += '.jpg'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + '.new'
    try:
        addresses = fetch_photos.ask(request, 4)
    except Exception as e:
        print('%-34s не спросилось: %s' % (target, e))
        return False
    for address in addresses:
        try:
            if fetch_photos.download(address, temp):
                os.replace(temp, path)
                print('%-34s заменён' % target)
                return True
        except Exception:
            continue
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        time.sleep(0.2)
    print('%-34s не нашлось ничего годного' % target)
    return False


def main():
    parsed = argparse.ArgumentParser()
    parsed.add_argument('цель', nargs='?', help='папка/имя снимка')
    parsed.add_argument('запрос', nargs='?', help='что искать по-английски')
    parsed.add_argument('--list', dest='список',
                        help='файл со списком «цель<TAB>запрос»')
    args = parsed.parse_args()

    tasks = []
    if args.items:
        with io.open(args.items, encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                target, _, request = line.partition('\t')
                tasks.append((target.strip(), request.strip()))
    elif args.target and args.request:
        tasks.append((args.target, args.request))
    else:
        parsed.error('нужны цель и запрос либо --list')

    replaced = sum(1 for target, request in tasks if replace(target, request))
    print('\nзаменено: %s из %s' % (replaced, len(tasks)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

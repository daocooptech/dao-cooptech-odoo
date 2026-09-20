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


def заменить(цель, запрос):
    """Скачать снимок по запросу и положить вместо `цель`."""
    путь = os.path.join(IMG_DIR, цель.replace('/', os.sep))
    if not путь.lower().endswith(('.jpg', '.jpeg', '.png')):
        путь += '.jpg'
    os.makedirs(os.path.dirname(путь), exist_ok=True)
    временный = путь + '.new'
    try:
        адреса = fetch_photos.спросить(запрос, 4)
    except Exception as e:
        print('%-34s не спросилось: %s' % (цель, e))
        return False
    for адрес in адреса:
        try:
            if fetch_photos.скачать(адрес, временный):
                os.replace(временный, путь)
                print('%-34s заменён' % цель)
                return True
        except Exception:
            continue
        finally:
            if os.path.exists(временный):
                os.remove(временный)
        time.sleep(0.2)
    print('%-34s не нашлось ничего годного' % цель)
    return False


def main():
    разбор = argparse.ArgumentParser()
    разбор.add_argument('цель', nargs='?', help='папка/имя снимка')
    разбор.add_argument('запрос', nargs='?', help='что искать по-английски')
    разбор.add_argument('--list', dest='список',
                        help='файл со списком «цель<TAB>запрос»')
    аргументы = разбор.parse_args()

    задания = []
    if аргументы.список:
        with io.open(аргументы.список, encoding='utf-8') as fh:
            for строка in fh:
                строка = строка.strip()
                if not строка or строка.startswith('#'):
                    continue
                цель, _, запрос = строка.partition('\t')
                задания.append((цель.strip(), запрос.strip()))
    elif аргументы.цель and аргументы.запрос:
        задания.append((аргументы.цель, аргументы.запрос))
    else:
        разбор.error('нужны цель и запрос либо --list')

    заменено = sum(1 for цель, запрос in задания if заменить(цель, запрос))
    print('\nзаменено: %s из %s' % (заменено, len(задания)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

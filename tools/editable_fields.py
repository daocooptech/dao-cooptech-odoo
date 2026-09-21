# -*- coding: utf-8 -*-
"""Какие поля на страницах портала правятся и как.

Зачем. Владелец 21 сентября 2026: «принцип редактирования устроен по
старому, нужно ко всем полям которые мы редактируем добавить иконку
карандаша… проверь весь портал». Проверять глазами восемнадцать модулей
— это день работы и всё равно с пропусками; разбор представлений даёт
точный список за секунду.

Что считается. Поле в форме, у которого нет `readonly="1"` и которое не
лежит внутри списка (`list`) — то есть то, что человек правит прямо на
странице. Для каждого видно, правится ли оно по месту (`coop_inline`,
`coop_about`) или по-старому — страничными кнопками сохранения.

    python tools/editable_fields.py            — сводка по модулям
    python tools/editable_fields.py coop.project   — по одной модели
"""
import io
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Виджеты правки по месту: карандаш, галочка, крестик.
ПО_МЕСТУ = ('coop_inline', 'coop_about', 'coop_contact_lines')

# Поля, которые правятся не строкой, а своим управлением, и карандаш им
# не нужен: изображение меняется щелчком по себе, состояние — кнопками
# в шапке, переключатель — самим переключателем.
СВОИ_УПРАВЛЕНИЯ = ('image', 'image_url', 'statusbar', 'boolean_toggle',
                   'progressbar', 'priority', 'radio', 'many2many_tags',
                   'coop_readiness_ring', 'coop_favorite')


def вычисляемые():
    """Модель → множество вычисляемых полей.

    Вычисляемое поле без обратной записи человек не правит: карандаш у
    него означал бы обещание, которого движок не выполнит. Берём из
    графа кода — он собирается разбором исходников (`tools/graph.py`).
    """
    путь = os.path.join(HERE, 'graph.json')
    if not os.path.exists(путь):
        return {}
    with io.open(путь, encoding='utf-8') as fh:
        граф = json.load(fh)
    таблица = {}
    for запись in граф.get('модели', []):
        модель = запись.get('модель')
        if not модель:
            continue
        свои = таблица.setdefault(модель, set())
        for поле in запись.get('поля', []):
            if поле.get('вычисляемое'):
                свои.add(поле.get('имя'))
    return таблица


def формы(путь):
    """Формы представлений в файле: (имя модели, узел формы)."""
    try:
        дерево = ET.parse(путь)
    except ET.ParseError:
        return []
    найдено = []
    for запись in дерево.getroot().iter('record'):
        if запись.get('model') != 'ir.ui.view':
            continue
        модель = ''
        for поле in запись.findall('field'):
            if поле.get('name') == 'model':
                модель = (поле.text or '').strip()
        for arch in запись.findall("field[@name='arch']"):
            for форма in arch.iter('form'):
                найдено.append((модель, форма))
    return найдено


def правимые(форма, вычисленные=()):
    """Поля формы, которые человек правит на странице."""
    внутри_списка = {id(узел) for список in форма.iter('list')
                     for узел in список.iter('field')}
    строки = []
    for поле in форма.iter('field'):
        if id(поле) in внутри_списка:
            continue
        if поле.get('readonly') == '1' or poле_невидимо(поле):
            continue
        виджет = поле.get('widget') or ''
        if виджет in СВОИ_УПРАВЛЕНИЯ:
            continue
        if поле.get('name') in вычисленные:
            continue
        строки.append((поле.get('name'), виджет))
    return строки


def poле_невидимо(поле):
    return поле.get('invisible') == '1'


def main():
    искомая = sys.argv[1] if len(sys.argv) > 1 else ''
    считаются = вычисляемые()
    итог = []
    for каталог, _папки, файлы in os.walk(ROOT):
        if os.sep + 'static' in каталог or os.sep + '.git' in каталог:
            continue
        for имя in файлы:
            if not имя.endswith('.xml'):
                continue
            путь = os.path.join(каталог, имя)
            for модель, форма in формы(путь):
                if искомая and модель != искомая:
                    continue
                поля = правимые(форма, считаются.get(модель, set()))
                if not поля:
                    continue
                по_месту = [п for п, в in поля if в in ПО_МЕСТУ]
                по_старому = [п for п, в in поля if в not in ПО_МЕСТУ]
                итог.append((модель, os.path.relpath(путь, ROOT),
                             len(по_месту), по_старому))

    итог.sort(key=lambda строка: (-len(строка[3]), строка[0]))
    всего_старых = sum(len(с[3]) for с in итог)
    print('форм с правимыми полями: %s, полей по-старому: %s'
          % (len(итог), всего_старых))
    for модель, путь, по_месту, по_старому in итог:
        print('\n%-26s %s' % (модель, путь))
        print('   по месту: %s | по-старому: %s' % (по_месту, len(по_старому)))
        if по_старому:
            print('   %s' % ', '.join(по_старому[:24]))
    return 0


if __name__ == '__main__':
    sys.exit(main())

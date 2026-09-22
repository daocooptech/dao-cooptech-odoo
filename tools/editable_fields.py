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
BY_PLACE = ('coop_inline', 'coop_block', 'coop_about', 'coop_contact_lines')

# Поля, которые правятся не строкой, а своим управлением, и карандаш им
# не нужен: изображение меняется щелчком по себе, состояние — кнопками
# в шапке, переключатель — самим переключателем.
OWN_CONTROLS = ('image', 'image_url', 'statusbar', 'boolean_toggle',
                   'progressbar', 'priority', 'radio', 'many2many_tags',
                   'coop_readiness_ring', 'coop_favorite', 'badge',
                   'percentage', 'monetary', 'float_time')


def computed():
    """Модель → множество вычисляемых полей.

    Вычисляемое поле без обратной записи человек не правит: карандаш у
    него означал бы обещание, которого движок не выполнит. Берём из
    графа кода — он собирается разбором исходников (`tools/graph.py`).
    """
    path = os.path.join(HERE, 'graph.json')
    if not os.path.exists(path):
        return {}
    with io.open(path, encoding='utf-8') as fh:
        graph = json.load(fh)
    table = {}
    for record in graph.get('модели', []):
        model = record.get('модель')
        if not model:
            continue
        own_list = table.setdefault(model, set())
        for field in record.get('поля', []):
            if field.get('вычисляемое'):
                own_list.add(field.get('имя'))
    return table


def forms(path):
    """Формы представлений в файле: (имя модели, узел формы)."""
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return []
    found = []
    for record in tree.getroot().iter('record'):
        if record.get('model') != 'ir.ui.view':
            continue
        model = ''
        for field in record.findall('field'):
            if field.get('name') == 'model':
                model = (field.text or '').strip()
        for arch in record.findall("field[@name='arch']"):
            for form in arch.iter('form'):
                found.append((model, form))
    return found


def editable(form, computed_list=()):
    """Поля формы, которые человек правит на странице.

    Полки на карточке — это встроенные канбаны, и поля в их шаблонах
    объявлены для показа, а не для правки: карандаш там был бы на
    плитке каталога. Список правится строкой, поиск — не правится вовсе.
    """
    inside_list = {id(node) for tag in ('list', 'kanban', 'search', 'templates')
                     for nested in form.iter(tag)
                     for node in nested.iter('field')}
    lines = []
    for field in form.iter('field'):
        if id(field) in inside_list:
            continue
        if field.get('readonly') == '1' or field_hidden(field):
            continue
        widget = field.get('widget') or ''
        if widget in OWN_CONTROLS:
            continue
        if field.get('name') in computed_list:
            continue
        lines.append((field.get('name'), widget))
    return lines


def field_hidden(field):
    return field.get('invisible') == '1'


def main():
    wanted = sys.argv[1] if len(sys.argv) > 1 else ''
    counted = computed()
    total = []
    for catalog, _folders, files in os.walk(ROOT):
        if os.sep + 'static' in catalog or os.sep + '.git' in catalog:
            continue
        for name in files:
            if not name.endswith('.xml'):
                continue
            path = os.path.join(catalog, name)
            for model, form in forms(path):
                if wanted and model != wanted:
                    continue
                fields = editable(form, counted.get(model, set()))
                if not fields:
                    continue
                by_place = [p for p, att in fields if att in BY_PLACE]
                old_way = [p for p, att in fields if att not in BY_PLACE]
                total.append((model, os.path.relpath(path, ROOT),
                             len(by_place), old_way))

    total.sort(key=lambda line: (-len(line[3]), line[0]))
    old_total = sum(len(ch[3]) for ch in total)
    print('форм с правимыми полями: %s, полей по-старому: %s'
          % (len(total), old_total))
    for model, path, by_place, old_way in total:
        print('\n%-26s %s' % (model, path))
        print('   по месту: %s | по-старому: %s' % (by_place, len(old_way)))
        if old_way:
            print('   %s' % ', '.join(old_way[:24]))
    return 0


if __name__ == '__main__':
    sys.exit(main())

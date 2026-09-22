# -*- coding: utf-8 -*-
"""Перевести поля формы на правку по месту — карандашом, а не страницей.

Зачем. Владелец 21 сентября 2026: «нужно ко всем полям которые мы
редактируем добавить иконку карандаша и редактирование происходит только
при нажатии… проверь весь портал». Полей таких по порталу четыре с
половиной сотни в полусотне форм: руками это день работы и всё равно с
пропусками, а правка механическая — тип поля решает, какой виджет.

Что делает. Для указанного файла представления дописывает каждому
правимому полю `widget="coop_inline"` (строка, дата, число, выбор,
связь) или `widget="coop_block"` (текст, разметка) и, если модель знает
про право правки, `readonly="not coop_can_edit"`.

Чего не трогает: поля внутри списков (там своя правка строкой), поля со
своим виджетом, невидимые, вычисляемые и те, у которых уже есть
`readonly`.

    python tools/to_inline_edit.py coop_events/views/coop_event_views.xml
    python tools/to_inline_edit.py --dry ...   — показать, ничего не меняя
"""
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

AS_LINE = {'Char', 'Date', 'Datetime', 'Integer', 'Float', 'Monetary',
           'Selection', 'Many2one'}
AS_BLOCK = {'Text', 'Html'}


def graph():
    path = os.path.join(HERE, 'graph.json')
    with io.open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    fields, computed, with_page = {}, {}, set()
    for record in data.get('модели', []):
        model = record.get('модель')
        if not model:
            continue
        inherits = record.get('наследует') or []
        if isinstance(inherits, str):
            inherits = [inherits]
        if 'coop.page.mixin' in inherits:
            with_page.add(model)
        own_list = fields.setdefault(model, {})
        account = computed.setdefault(model, set())
        for field in record.get('поля', []):
            own_list[field.get('имя')] = field.get('тип')
            if field.get('вычисляемое'):
                account.add(field.get('имя'))
    return fields, computed, with_page


def form_model(text, position):
    """Модель той записи представления, внутри которой лежит форма.

    По первой модели в файле определять нельзя: рядом со страницей в том
    же файле живут окна мастеров, и у них своя модель. На складчине из-за
    этого страница разбиралась по полям окна «Присоединиться».
    """
    start = text.rfind('<record', 0, position)
    if start < 0:
        return ''
    chunk = text[start:position]
    match = re.search(r'<field name="model">([^<]+)</field>', chunk)
    return match.group(1) if match else ''


def in_foreign(text, position):
    """Лежит ли поле в канбане, списке или поиске — там правки нет."""
    for tag in ('list', 'kanban', 'search', 'templates'):
        is_open = text.rfind('<%s' % tag, 0, position)
        if is_open < 0:
            continue
        is_closed = text.rfind('</%s>' % tag, 0, position)
        if is_closed < is_open:
            return True
    return False


# Окно создания — не страница: там заполняют новую запись целиком и
# нажимают «Сохранить» внизу, и карандаш у каждого поля означал бы, что
# запись уже есть. Узнаём по `<footer>` — в Odoo это признак диалога — и
# по имени представления.
WINDOW = re.compile(r'wizard|create|add_|_add|respond|apply|contribute|quick|join',
                  re.I)


def page_forms(text):
    """Куски текста, относящиеся к формам-страницам, парами (начало, конец)."""
    chunks = []
    for match in re.finditer(r'<form[^>]*>.*?</form>', text, re.S):
        chunk = match.group(0)
        if '<footer' in chunk:
            continue
        # Имя записи представления ищем перед формой — по нему видно
        # мастера и окна добавления.
        start = text.rfind('<record', 0, match.start())
        heading = text[start:match.start()] if start >= 0 else ''
        if WINDOW.search(heading):
            continue
        chunks.append((match.start(), match.end()))
    return chunks


def translate(path, field_type, computed, with_page, dry=False):
    with io.open(path, encoding='utf-8') as fh:
        text = fh.read()
    pages = page_forms(text)
    models = {start: form_model(text, start) for start, _ in pages}
    model = ', '.join(sorted({m for m in models.values() if m})) or '—'
    # Право правки есть там, где подмешана «страница записи»: поле
    # `coop_can_edit` объявлено в самой примеси, и в разборе модели его
    # не видно — видно только саму примесь в списке наследования.
    edits = []
    for match in re.finditer(r'<field\s+name="([a-z_0-9]+)"([^>]*?)(/?)>', text):
        name, tail, is_closed = match.group(1), match.group(2), match.group(3)
        if 'widget=' in tail or 'invisible="1"' in tail:
            continue
        # `readonly="1"` — поле показывают, а не правят; условие вида
        # `readonly="not coop_can_edit"` карандашу не мешает: виджет
        # сам прячет кнопку, когда править нельзя.
        if 'readonly="1"' in tail:
            continue
        if in_foreign(text, match.start()):
            continue
        own_item = [start for start, end in pages
                if start <= match.start() < end]
        if not own_item:
            continue
        field_model = models.get(own_item[0], '')
        type_codes = field_type.get(field_model, {})
        counted = computed.get(field_model, set())
        is_editable = field_model in with_page or 'coop_can_edit' in type_codes
        if name in counted or name not in type_codes:
            continue
        type_code = type_codes.get(name)
        if type_code in AS_LINE:
            widget = 'coop_inline'
        elif type_code in AS_BLOCK:
            widget = 'coop_block'
        else:
            continue
        addition = ' widget="%s"' % widget
        # Своё условие у поля уже есть — второе `readonly` в том же теге
        # это сломанный XML, а не двойная проверка.
        if is_editable and 'readonly=' not in tail:
            addition += ' readonly="not coop_can_edit"'
        new_one = '<field name="%s"%s%s%s>' % (name, tail, addition, is_closed)
        edits.append((match.start(), match.end(), new_one,
                       name, type_code, widget))

    # Заменяем с конца и по месту: одно и то же объявление поля
    # встречается и в канбане, и в списке, и в форме, а замена по
    # строке попала бы в первое вхождение — то есть в карточку
    # каталога, где карандашу не место.
    for start, end, new_one, *_ in reversed(edits):
        text = text[:start] + new_one + text[end:]
    if edits and not dry:
        with io.open(path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
    print('%s — %s (%s)' % (os.path.relpath(path, ROOT), model, len(edits)))
    for _start, _end, _new, name, type_code, widget in edits:
        print('    %-28s %-10s -> %s' % (name, type_code, widget))
    return len(edits)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry = '--dry' in sys.argv
    type_codes, counted, with_page = graph()
    count_all = 0
    for path in args:
        full = path if os.path.isabs(path) else os.path.join(ROOT, path)
        count_all += translate(full, type_codes, counted, with_page, dry)
    print('\nвсего полей переведено: %s%s' % (count_all, ' (показ)' if dry else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())

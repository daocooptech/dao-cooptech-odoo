# -*- coding: utf-8 -*-
"""Проверка правок поверх движка: то, что ловится без браузера.

Зачем. 22 сентября 2026 три ошибки подряд уронили каталоги платформы, и
все три ловились здесь, не доходя до боевой:

* два шаблона под одним именем — кто зарегистрируется последним, тот и
  остался;
* объект заплатки, приложенный к двум прототипам, и он же скопированный
  через расширение — движок запрещает и то и другое прямым текстом
  (`developer/reference/frontend/patching_code`, «Applying the same patch
  to multiple objects»);
* прицел `xpath`, попадающий не в один узел, а в ноль или в два.

Отдельная проверка нужна потому, что ни одна из этих бед не видна ни
питону, ни серверу: наследование шаблонов применяется **в браузере**, а
заплатки — при загрузке пакета. До этого момента всё выглядит исправным.

Запуск:

    python tools/check_theme.py            # из coop-addons
    python tools/check_theme.py --odoo ПУТЬ  # где лежит движок

Возвращает ненулевой код, если нашла беду, — чтобы вставать в pre-commit.
"""
import argparse
import io
import os
import re
import sys

try:
    from lxml import etree
except ImportError:  # pragma: no cover
    etree = None

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS = os.path.dirname(HERE)
DEFAULT_ODOO = os.path.join(os.path.dirname(ADDONS), 'odoo')


def our_xml_templates():
    """Наши файлы шаблонов: те, что лежат в static/src/xml."""
    out = []
    for root, dirs, files in os.walk(ADDONS):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules')]
        if os.path.join('static', 'src', 'xml') not in root:
            continue
        for name in files:
            if name.endswith('.xml'):
                out.append(os.path.join(root, name))
    return sorted(out)


def our_js_files():
    out = []
    for root, dirs, files in os.walk(ADDONS):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules')]
        if os.path.join('static', 'src') not in root:
            continue
        for name in files:
            if name.endswith('.js'):
                out.append(os.path.join(root, name))
    return sorted(out)


def check_duplicate_names(problems):
    """Одно имя шаблона — один шаблон."""
    seen = {}
    for path in our_xml_templates():
        try:
            tree = etree.parse(path)
        except Exception as error:
            problems.append('%s: не разбирается как XML: %s' % (path, error))
            continue
        for node in tree.getroot():
            name = node.get('t-name')
            if not name:
                continue
            if name in seen:
                problems.append(
                    'Имя шаблона «%s» занято дважды:\n    %s\n    %s\n'
                    '    Кто зарегистрируется последним, тот и останется. '
                    'Дайте второму своё имя.' % (name, seen[name], path))
            else:
                seen[name] = path
    return seen


def odoo_templates(odoo_root):
    """Имя шаблона → разобранный узел, по всем статическим файлам движка."""
    found = {}
    if not os.path.isdir(odoo_root):
        return found
    for root, dirs, files in os.walk(odoo_root):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules')]
        if 'static' not in root:
            continue
        for name in files:
            if not name.endswith('.xml'):
                continue
            path = os.path.join(root, name)
            try:
                tree = etree.parse(path)
            except Exception:
                continue
            for node in tree.getroot():
                tname = node.get('t-name')
                if tname and tname not in found:
                    # Каждый шаблон — в свой документ.
                    #
                    # В xpath `//button` ищет от корня ДОКУМЕНТА, а не от
                    # узла, на котором его зовут. Если оставить все шаблоны
                    # файла в одном документе, прицел одного шаблона видит
                    # узлы соседних — и проверка врёт про «попадает в два».
                    # Движок этой беды не знает: он держит каждый шаблон
                    # отдельно. Проверка обязана повторять его устройство,
                    # иначе меряет не то.
                    found[tname] = etree.fromstring(etree.tostring(node))
    return found


HASCLASS = re.compile(r"hasclass\(([^)]*)\)")


def expand_hasclass(expr):
    """Перевести `hasclass('a','b')` в обычный xpath.

    `hasclass` — расширение движка, стандартный xpath его не знает. Движок
    делает ровно такую же замену у себя в браузере
    (`web/static/src/core/template_inheritance.js`), поэтому и проверка
    должна знать её, иначе половина прицелов не проверится вовсе.
    """
    def replace(m):
        классы = [c.strip().strip('\'"') for c in m.group(1).split(',')]
        куски = ["contains(concat(' ', normalize-space(@class), ' '), ' %s ')"
                 % c for c in классы if c]
        return ' and '.join(куски) if куски else 'true()'
    return HASCLASS.sub(replace, expr)


def check_xpaths(problems, odoo_root, ours):
    """Прицел наследования обязан попадать ровно в один узел."""
    base = odoo_templates(odoo_root)
    if not base:
        problems.append(
            'Движок не найден в %s — прицелы xpath не проверены. '
            'Укажите путь ключом --odoo.' % odoo_root)
        return
    for path in our_xml_templates():
        try:
            tree = etree.parse(path)
        except Exception:
            continue
        for node in tree.getroot():
            target = node.get('t-inherit')
            if not target:
                continue
            base_node = base.get(target)
            if base_node is None:
                # Может наследовать наш же шаблон — тогда ищем среди своих.
                if target in ours:
                    continue
                problems.append(
                    '%s: шаблон «%s» наследует «%s», а такого нет ни у '
                    'движка, ни у нас.' % (path, node.get('t-name'), target))
                continue
            for op in node.iter('xpath'):
                expr = op.get('expr')
                if not expr:
                    continue
                try:
                    hits = base_node.xpath(expand_hasclass(expr))
                except Exception as error:
                    problems.append('%s: прицел «%s» не разбирается: %s'
                                    % (path, expr, error))
                    continue
                if len(hits) != 1:
                    problems.append(
                        '%s: шаблон «%s», прицел\n    %s\n'
                        '    попадает в %d узлов, а должен ровно в один.\n'
                        '    Ноль — правило молча не применится; больше '
                        'одного — применится к первому, и это не обязательно '
                        'тот, о ком вы думали.'
                        % (path, node.get('t-name'), expr, len(hits)))


def patch_calls(text):
    """Найти вызовы `patch(что, чем)` и вернуть (строка, что, чем).

    Своим разбором, а не одним выражением: аргументы бывают со скобками
    внутри — вызов функции, объект с методами, — и выражение, обрывающееся
    на первой закрывающей скобке, режет их посередине. На этом проверка
    сперва ругалась на исправный код.
    """
    out = []
    i = 0
    while True:
        i = text.find('patch(', i)
        if i < 0:
            return out
        if i and (text[i - 1].isalnum() or text[i - 1] in '_$.'):
            i += 6  # `unpatch(`, `coopPatch(` — не наш вызов
            continue
        j = i + 6
        глубина = 1
        запятая = None
        while j < len(text) and глубина:
            c = text[j]
            if c in '([{':
                глубина += 1
            elif c in ')]}':
                глубина -= 1
            elif c == ',' and глубина == 1 and запятая is None:
                запятая = j
            j += 1
        if глубина or запятая is None:
            return out
        строка = text[:i].count('\n') + 1
        out.append((строка,
                    text[i + 6:запятая].strip(),
                    text[запятая + 1:j - 1].strip()))
        i = j


def check_patches(problems):
    """Объект заплатки — один раз и без копий.

    Оба запрета описаны в документации движка
    (`developer/reference/frontend/patching_code`, раздел «Applying the
    same patch to multiple objects»): объект можно приложить только один
    раз, и копировать его нельзя — `super` внутри копии указывает не туда.
    """
    for path in our_js_files():
        text = io.open(path, encoding='utf-8').read()
        вызовы = patch_calls(text)
        имена = {чем for _, _, чем in вызовы if чем.isidentifier()}
        использовано = {}
        for строка, куда, чем in вызовы:
            # Копия объекта, который где-то здесь же прикладывают заплаткой.
            копия = None
            if чем.startswith('{'):
                for имя in имена:
                    if '...' + имя in чем.replace(' ', ''):
                        копия = имя
                        break
            if копия:
                problems.append(
                    '%s:%d: заплатка собрана копией «...%s».\n'
                    '    Движок это запрещает: при копии `super` перестаёт '
                    'указывать куда надо.\n'
                    '    Нужна функция, возвращающая каждый раз новый объект '
                    '— см. patching_code, «Applying the same patch to '
                    'multiple objects».' % (path, строка, копия))
                continue
            if not чем.isidentifier():
                # Литерал на месте или вызов функции — каждый раз своё.
                continue
            if чем in использовано:
                problems.append(
                    '%s:%d: объект «%s» уже приложен заплаткой в строке %d.\n'
                    '    Один объект можно приложить только один раз: `super` '
                    'внутри него запомнит последний прототип.\n'
                    '    Сделайте функцию, возвращающую новый объект.'
                    % (path, строка, чем, использовано[чем]))
            else:
                использовано[чем] = строка


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--odoo', default=DEFAULT_ODOO,
                        help='где лежит движок Odoo')
    args = parser.parse_args()

    if etree is None:
        print('Нужен lxml: pip install lxml')
        return 2

    problems = []
    ours = check_duplicate_names(problems)
    check_xpaths(problems, args.odoo, ours)
    check_patches(problems)

    if not problems:
        print('Проверка темы: бед нет.')
        return 0
    print('Проверка темы: бед %d\n' % len(problems))
    for item in problems:
        print('— ' + item)
        print()
    return 1


if __name__ == '__main__':
    sys.exit(main())

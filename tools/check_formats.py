# -*- coding: utf-8 -*-
"""Подстановки в строках должны совпадать с именами аргументов.

Зачем. 22 сентября 2026 переименование кириллических имён латиницей
(решение 368) сделало ровно эту беду в трёх местах: аргументы стали
`org=`, `who=`, а подстановки в самой строке остались `%(орг)s`,
`%(кто)s` — строк переименователь не трогает, и правильно делает.

Получился код, который компилируется, проходит любую проверку синтаксиса
и падает `KeyError` только в тот момент, когда человек нажал кнопку. Три
таких места нашлись случайно; четвёртое нашла бы боевая.

Проверяются вызовы вида `_('...%(имя)s...', имя=...)` и
`'...%(имя)s...' % {...}` — то есть именованные подстановки, у которых
имена видны обеим сторонам. Позиционные `%s` тут не при чём.

Запуск из `coop-addons`:

    python tools/check_formats.py

Возвращает ненулевой код, если нашла расхождение, — чтобы вставать в
ворота выкатки рядом с `check_theme.py`.
"""
import ast
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS = os.path.dirname(HERE)

PLACEHOLDER = re.compile(r'%\(([^)]+)\)')


def py_files(root):
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in ('.git', '__pycache__', 'node_modules')]
        for name in files:
            if name.endswith('.py'):
                yield os.path.join(base, name).replace(os.sep, '/')


def text_of(node):
    """Склеить строковый литерал, в том числе разбитый на куски.

    Строки в этом коде часто разложены по строчкам ради ширины:
    `'начало ' 'продолжение'`. Разборщик уже склеил их в один узел, но
    f-строки приходят по частям.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
        return ''.join(out)
    return None


def check_call(path, node, problems):
    """`_('...%(имя)s...', имя=...)` — имена обязаны совпасть."""
    if not node.args or not node.keywords:
        return
    template = text_of(node.args[0])
    if not template:
        return
    wanted = set(PLACEHOLDER.findall(template))
    if not wanted:
        return
    given = {kw.arg for kw in node.keywords if kw.arg}
    # `**словарь` — имена известны только в работе, проверить нечем.
    if any(kw.arg is None for kw in node.keywords):
        return
    missing = wanted - given
    if missing:
        problems.append(
            '%s:%d: в строке есть %s, а среди аргументов их нет.\n'
            '    Дано: %s\n'
            '    Это падает `KeyError` в тот момент, когда человек нажал '
            'кнопку, — не раньше.'
            % (path, node.lineno,
               ', '.join('%%(%s)s' % m for m in sorted(missing)),
               ', '.join(sorted(given)) or '—'))


def check_percent(path, node, problems):
    """`'...%(имя)s...' % {'имя': ...}` — то же самое, другой записью."""
    if not isinstance(node.op, ast.Mod):
        return
    template = text_of(node.left)
    if not template:
        return
    wanted = set(PLACEHOLDER.findall(template))
    if not wanted or not isinstance(node.right, ast.Dict):
        return
    given = set()
    for key in node.right.keys:
        name = text_of(key)
        if name is None:
            return  # ключ считается на ходу — судить не берёмся
        given.add(name)
    missing = wanted - given
    if missing:
        problems.append(
            '%s:%d: в строке есть %s, а в словаре таких ключей нет.\n'
            '    Дано: %s'
            % (path, node.lineno,
               ', '.join('%%(%s)s' % m for m in sorted(missing)),
               ', '.join(sorted(given)) or '—'))


def main():
    problems = []
    for path in sorted(py_files(ADDONS)):
        try:
            tree = ast.parse(io.open(path, encoding='utf-8').read())
        except SyntaxError as error:
            problems.append('%s: не разбирается: %s' % (path, error))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                check_call(path, node, problems)
            elif isinstance(node, ast.BinOp):
                check_percent(path, node, problems)

    if not problems:
        print('Подстановки в строках: бед нет.')
        return 0
    print('Подстановки в строках: бед %d\n' % len(problems))
    for item in problems:
        print('— ' + item)
        print()
    return 1


if __name__ == '__main__':
    sys.exit(main())

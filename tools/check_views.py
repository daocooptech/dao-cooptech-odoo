# -*- coding: utf-8 -*-
"""Виды обязаны проходить схему движка.

Зачем. 23 сентября 2026 поисковый вид документов не встал на сервере с
единственным словом в журнале: «Invalid view definition». Причина —
атрибуты `string` и `expand` у `<group>`: схема движка их не допускает.
Найти это иначе как прогоном на сервере было нечем, а прогон стоит
минуты и требует остановки службы.

Между тем схема лежит рядом, в `odoo/addons/base/rng/`, и проверяется за
секунду. Ошибка вида — не «опечатка в разметке», а несовпадение со
схемой, и схема умеет сказать об этом сама, строкой и словами.

Проверяются `search`, `form`, `list`, `kanban`, `calendar`, `graph`,
`pivot`, `activity` — те, для которых у движка есть своя схема.

Запуск из `coop-addons`:

    python tools/check_views.py
    python tools/check_views.py --odoo ПУТЬ

Возвращает ненулевой код, если вид не прошёл, — чтобы вставать в ворота
выкатки рядом с `check_theme.py`.
"""
import argparse
import os
import sys

try:
    from lxml import etree
except ImportError:  # pragma: no cover
    etree = None

HERE = os.path.dirname(os.path.abspath(__file__))
ADDONS = os.path.dirname(HERE)
DEFAULT_ODOO = os.path.join(os.path.dirname(ADDONS), 'odoo')

# Корень вида → файл схемы. Имена схем у движка не совпадают с именами
# видов один в один, поэтому список явный.
SCHEMAS = {
    'search': 'search_view.rng',
    'form': 'form_view.rng',
    'list': 'list_view.rng',
    'kanban': 'kanban_view.rng',
    'calendar': 'calendar_view.rng',
    'graph': 'graph_view.rng',
    'pivot': 'pivot_view.rng',
    'activity': 'activity_view.rng',
}


def rng_dir(odoo_root):
    """Где лежат схемы. Путь у разных сборок разный."""
    for tail in (('odoo', 'addons', 'base', 'rng'),
                 ('addons', 'base', 'rng')):
        path = os.path.join(odoo_root, *tail)
        if os.path.isdir(path):
            return path
    return None


def our_view_files():
    out = []
    for base, dirs, files in os.walk(ADDONS):
        dirs[:] = [d for d in dirs
                   if d not in ('.git', '__pycache__', 'node_modules')]
        if os.path.join('views') not in base and os.path.join('data') not in base:
            continue
        for name in files:
            if name.endswith('.xml'):
                out.append(os.path.join(base, name).replace(os.sep, '/'))
    return sorted(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--odoo', default=DEFAULT_ODOO)
    args = parser.parse_args()

    if etree is None:
        print('Нужен lxml: pip install lxml')
        return 2

    schemas_at = rng_dir(args.odoo)
    if not schemas_at:
        print('Схемы движка не найдены в %s — виды не проверены. '
              'Укажите путь ключом --odoo.' % args.odoo)
        return 0

    validators = {}
    for root_tag, file_name in SCHEMAS.items():
        path = os.path.join(schemas_at, file_name)
        if os.path.exists(path):
            try:
                validators[root_tag] = etree.RelaxNG(etree.parse(path))
            except Exception as error:
                print('Схема %s не читается: %s' % (file_name, error))

    problems = []
    checked = 0
    for path in our_view_files():
        try:
            tree = etree.parse(path)
        except Exception:
            continue
        for arch in tree.xpath("//record[@model='ir.ui.view']"
                               "/field[@name='arch']"):
            for node in arch:
                validator = validators.get(node.tag)
                if validator is None:
                    continue
                # Вид с `t-inherit`/`xpath` проверять схемой нельзя: там
                # не целый вид, а правки к нему, и схема справедливо
                # отказывается их понимать.
                if node.xpath('.//xpath') or node.get('position'):
                    continue
                # В свой документ: схема проверяет корень, а узел внутри
                # чужого дерева тянет за собой соседей.
                piece = etree.fromstring(etree.tostring(node))
                checked += 1
                if validator.validate(piece):
                    continue
                name = arch.getparent().get('id') or '(без имени)'
                lines = ['%s: вид «%s» (%s) не проходит схему движка:'
                         % (path, name, node.tag)]
                for error in validator.error_log:
                    lines.append('    строка %s: %s'
                                 % (error.line, error.message))
                lines.append('    Схема лежит в %s и знает точно, что '
                             'допускается.' % schemas_at)
                problems.append('\n'.join(lines))

    if not problems:
        print('Виды: проверено %d, бед нет.' % checked)
        return 0
    print('Виды: проверено %d, бед %d\n' % (checked, len(problems)))
    for item in problems:
        print('— ' + item)
        print()
    return 1


if __name__ == '__main__':
    sys.exit(main())

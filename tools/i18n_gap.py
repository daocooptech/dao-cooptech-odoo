#!/usr/bin/env python3
"""Непереведённое в ru.po движка 20 — замер, выгрузка пачки, вливание.

Задача 288 (владелец 19.10.2026: «я вижу английские слова, мы вроде
договаривались перевести всё, что видит пользователь»). Перевод кладётся
в ru.po форка движка (ветка 20.0-coop) — решение владельца 19.10.

    python tools/i18n_gap.py measure  installed.txt [--same] # по списку модулей
    python tools/i18n_gap.py extract  batch.json sale crm …  # пустые msgid пачки
    python tools/i18n_gap.py extract  batch.json --same sale … # и «переведённые» английским
    python tools/i18n_gap.py merge    batch.json done.json   # перевод → ru.po

Пакет — `{"k": "sale#12", "src": …, "plural": …, "ctx": …, "where": …}`;
ответ переводчика — `{"sale#12": "…"}`, у множественного числа —
список из трёх форм (1, 2–4, 5+). Вливание пишет только в пустой
`msgstr ""`: файл не переформатируется, дифф — ровно переведённые строки.
Перевод, где подстановки (`%s`, `%(имя)s`, `{имя}`) или теги не совпали
с оригиналом, не вливается и печатается.

Запускать интерпретатором venv: нужен polib (он есть у Odoo).
"""
import collections
import json
import os
import re
import sys

import polib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))  # rudoo20/
PATHS = [os.path.join(ROOT, 'coop-addons'), os.path.join(ROOT, 'coop-addons', 'forks'),
         os.path.join(ROOT, 'odoo', 'addons'), os.path.join(ROOT, 'odoo', 'odoo', 'addons')]


def module_dir(mod):
    for base in PATHS:
        path = os.path.join(base, mod)
        if os.path.isfile(os.path.join(path, '__manifest__.py')):
            return path
    return None


def ru_po(mod):
    path = module_dir(mod)
    return os.path.join(path, 'i18n', 'ru.po') if path else None


def _latin(text):
    """Есть ли в тексте английские слова — без тегов и подстановок."""
    return re.search(r'[A-Za-z]{3,}', re.sub(r'<[^>]+>|%\([^)]*\)[sdif]|\{[^}]*\}|&\w+;', '', text))


def empty_entries(path, same=False):
    """Записи без перевода: не устаревшие, не «fuzzy», msgstr пуст.

    С `same` — ещё и «переведённые» самим английским оригиналом
    (`msgid "OTD"` → `msgstr "OTD"`): на экране они такие же английские.
    """
    po = polib.pofile(path, wrapwidth=0)
    out = []
    for entry in po:
        if entry.obsolete or 'fuzzy' in entry.flags or not entry.msgid:
            continue
        if entry.msgid_plural:
            if not any(entry.msgstr_plural.values()):
                out.append(entry)
        elif not entry.msgstr:
            out.append(entry)
        elif same and entry.msgstr == entry.msgid and _latin(entry.msgid):
            out.append(entry)
    return out


def measure(listfile, same=False):
    mods = [line.strip() for line in open(listfile, encoding='utf-8') if line.strip()]
    rows, total = [], collections.Counter()
    for mod in mods:
        path = ru_po(mod)
        if not path or not os.path.isfile(path):
            continue
        count = len(empty_entries(path, same))
        src = 'coop' if os.sep + 'coop-addons' in path or '/coop-addons' in path else 'odoo'
        total[src] += count
        rows.append((count, mod, src))
    # Ноль по всем модулям при непустом списке — скорее сломанный замер.
    if mods and not rows:
        sys.exit('i18n_gap: ни одного ru.po не найдено — проверь пути')
    for count, mod, src in sorted(rows, reverse=True):
        if count:
            print(count, mod, src)
    print('итого', dict(total))


def extract(out, mods, same=False):
    batch = []
    for mod in mods:
        path = ru_po(mod)
        if not path or not os.path.isfile(path):
            print('нет ru.po:', mod)
            continue
        for index, entry in enumerate(empty_entries(path, same)):
            where = (entry.occurrences[0][0] if entry.occurrences else '')
            batch.append({'k': '%s#%d' % (mod, entry.linenum), 'src': entry.msgid,
                          'plural': entry.msgid_plural or None, 'ctx': entry.msgctxt or None,
                          'where': where[:80]})
    with open(out, 'w', encoding='utf-8') as handle:
        json.dump(batch, handle, ensure_ascii=False, indent=0)
    print('выгружено', len(batch), 'в', out)


PLACEHOLDER = re.compile(r'%\([^)]+\)[sdif]|%[sdif]|\{\{[^}]*\}\}|\{[A-Za-z_][\w.]*\}|\$\{[^}]*\}')
TAG = re.compile(r'</?([a-zA-Z][\w-]*)')


def signature(text):
    return (collections.Counter(PLACEHOLDER.findall(text)),
            collections.Counter(t.lower() for t in TAG.findall(text)))


def quote(text):
    return '"%s"' % text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')


def mod_of(path):
    return os.path.basename(os.path.dirname(os.path.dirname(path)))


def merge(batchfile, donefile):
    batch = {item['k']: item for item in json.load(open(batchfile, encoding='utf-8'))}
    done = json.load(open(donefile, encoding='utf-8'))
    by_file = collections.defaultdict(dict)
    rejected = []
    for key, value in done.items():
        item = batch.get(key)
        if not item:
            rejected.append((key, 'нет в пакете'))
            continue
        forms = value if isinstance(value, list) else [value]
        if item['plural'] and len(forms) != 3:
            rejected.append((key, 'у множественного числа нужно три формы'))
            continue
        if not all(isinstance(f, str) and f.strip() for f in forms):
            rejected.append((key, 'пустой перевод'))
            continue
        # Код, формат, бренд оставлены как есть — писать их незачем: пустой
        # msgstr и так показывает оригинал.
        if forms == [item['src']]:
            continue
        bad = False
        for form in forms:
            # У множественного числа форма «1» вправе опустить %d.
            src = item['src'] if form is forms[0] else (item['plural'] or item['src'])
            want_ph, want_tags = signature(src)
            got_ph, got_tags = signature(form)
            if want_tags != got_tags or (want_ph != got_ph and not (item['plural'] and form is forms[0])):
                rejected.append((key, 'подстановки/теги: %r → %r' % (src[:60], form[:60])))
                bad = True
                break
        if bad:
            continue
        mod, line = key.rsplit('#', 1)
        by_file[ru_po(mod)][int(line)] = forms
    written = 0
    for path, entries in by_file.items():
        lines = open(path, encoding='utf-8').read().split('\n')
        for start, forms in entries.items():
            i = start - 1
            # От строки msgid вниз до msgstr; пустой — «msgstr ""» без продолжения.
            while i < len(lines) and not lines[i].startswith('msgstr'):
                i += 1
            for n, form in enumerate(forms):
                head = 'msgstr[%d] ' % n if lines[i].startswith('msgstr[') else 'msgstr '
                # Пустой msgstr или ровно английский оригинал одной строкой.
                item = batch['%s#%d' % (mod_of(path), start)]
                fits = lines[i] in (head + '""', head + quote(item['src']))
                if not fits or (i + 1 < len(lines) and lines[i + 1].startswith('"')):
                    rejected.append(('%s:%d' % (os.path.basename(os.path.dirname(os.path.dirname(path))), start),
                                     'msgstr уже не пуст'))
                    break
                lines[i] = head + quote(form)
                i += 1
            else:
                written += 1
        with open(path, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write('\n'.join(lines))
    print('влито', written, 'отклонено', len(rejected))
    for key, why in rejected[:60]:
        print('  ', key, why)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    command = sys.argv[1]
    if command == 'measure':
        measure(sys.argv[2], same='--same' in sys.argv)
    elif command == 'extract':
        args = [a for a in sys.argv[3:] if a != '--same']
        extract(sys.argv[2], args, same='--same' in sys.argv)
    elif command == 'merge':
        merge(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)

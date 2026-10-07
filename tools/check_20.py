# -*- coding: utf-8 -*-
"""Ворота линии 20: то, что в Odoo 20 ломается молча или роняет экран.

Каждое правило — измеренная поломка из описи переезда
(Матчасть/decentralized-dev/2026-10-06 — Переезд на Odoo 20 — опись и план).
Ни одну из них не ловят ни питон, ни схема видов, ни установка модуля:
t-esc выводит пустоту, значок fa- — пустой квадрат, 'datas' тихо
отбрасывается, static props роняет весь веб-клиент уже в браузере.

    python tools/check_20.py            # сводка по правилам и модулям
    python tools/check_20.py -v         # плюс каждое место: файл:строка
    python tools/check_20.py --rule t-esc -v

Код возврата 1, если нашлось хоть одно место.
"""
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', 'tools'}
# Миграция переводит записанные в базу имена Font Awesome — старые имена
# в ней и есть то, что она ищет.
FA_EXEMPT_DIR = os.sep + 'migrations' + os.sep
# Свой протокол федерации кодирует base64 не для полей Binary.
B64_EXEMPT = ('coop_federation' + os.sep,)

# имя -> (расширения, регулярка, пояснение)
RULES = {
    't-esc': (('.xml',), re.compile(r'\bt-(?:esc|raw)\s*='),
              'в 20 нет t-esc/t-raw: серверный QWeb выводит пустоту — t-out (+ Markup)'),
    'fa-icon': (('.xml', '.js', '.py', '.scss', '.html'),
                re.compile(r'(?<![\w-])fa(?:\s+|-)(?!ma\b)[a-z][\w-]*'),
                'Font Awesome в ядре 20 нет — Material Symbols (решение 445 п. 18)'),
    'datas': (('.py',), re.compile(r'''['"]datas['"]'''),
              'ir.attachment.datas удалено и при create тихо отбрасывается — raw'),
    'get_param': (('.py',), re.compile(r'\.(?:get|set)_param\('),
                  'get_param/set_param удалены — get_str/get_bool/get_int/set_*'),
    'b64-bytes': (('.py',), re.compile(r'b64encode\((?!.*\.decode\()'),
                  'bytes в поле Binary — TypeError: .decode() при записи'),
    'static-props': (('.js',), re.compile(r'\bstatic\s+(?:props|defaultProps)\s*='),
                     'Owl 3: static props/defaultProps роняют веб-клиент — useProps'),
    'owl2-state': (('.js',), re.compile(
        r'''import\s*\{[^}]*\b(?:useState|reactive)\b[^}]*\}\s*from\s*['"]@odoo/owl['"]'''),
        'Owl 3: useState/reactive нет — proxy (служба с reactive роняет весь веб-клиент)'),
    'mail-paths': (('.js',), re.compile(
        r'''@mail/(?:core/common/record|chatter/web_portal/chatter|utils/common/pdf_thumbnail|core/public_web/messaging_menu)['"]'''),
        'путь модуля mail в 20 переехал или удалён'),
    'store-api': (('.py',), re.compile(r'\b_to_store_defaults\b|\._action_unfollow\('),
                  'Discuss Store: _to_store_defaults и _action_unfollow удалены'),
    'pycompat': (('.py',), re.compile(r'odoo\.tools\s+import\s+pycompat|odoo\.tools\.pycompat'),
                 'odoo.tools.pycompat в 20 нет'),
    'ir-rule': (('.xml', '.csv'), re.compile(r'model=["\']ir\.rule["\']|^id,name,model_id:id,group_id:id,perm_'),
                'ir.model.access и ir.rule заменены на ir.access'),
}


def module_of(path):
    rel = os.path.relpath(path, ROOT)
    parts = rel.split(os.sep)
    return parts[1] if parts[0] == 'forks' and len(parts) > 1 else parts[0]


def scan(only=None):
    hits = defaultdict(list)  # rule -> [(path, lineno, line)]
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = os.path.join(base, name)
            ext = os.path.splitext(name)[1]
            rules = [r for r, (exts, _, _) in RULES.items()
                     if ext in exts and (only is None or r == only)]
            if not rules:
                continue
            try:
                with open(path, encoding='utf-8') as f:
                    lines = f.read().split('\n')
            except (UnicodeDecodeError, OSError):
                continue
            rel = os.path.relpath(path, ROOT)
            for rule in rules:
                if rule == 'b64-bytes' and rel.startswith(B64_EXEMPT):
                    continue
                if rule == 'fa-icon' and FA_EXEMPT_DIR in os.sep + rel:
                    continue
                rx = RULES[rule][1]
                for i, line in enumerate(lines, 1):
                    if rx.search(line):
                        hits[rule].append((rel, i, line.strip()))
    return hits


def main(argv):
    # Консоль Windows по умолчанию в cp1251 — кириллица выходит кракозябрами.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    verbose = '-v' in argv
    only = argv[argv.index('--rule') + 1] if '--rule' in argv else None
    if only and only not in RULES:
        print('нет такого правила: %s (есть: %s)' % (only, ', '.join(RULES)))
        return 2
    # Независимая проба: сколько файлов вообще под ворота попадает. Ноль
    # файлов при нуле находок — сломанные ворота, а не чистый код.
    seen = sum(1 for b, d, fs in os.walk(ROOT) for f in fs
               if f.endswith(('.py', '.xml', '.js')) and '.git' not in b)
    if not seen:
        print('ВОРОТА СЛОМАНЫ: не найдено ни одного файла в %s' % ROOT)
        return 2
    hits = scan(only)
    total = 0
    for rule, (_, _, why) in RULES.items():
        if only and rule != only:
            continue
        found = hits.get(rule, [])
        total += len(found)
        if not found:
            print('%-13s 0' % rule)
            continue
        by_mod = Counter(module_of(os.path.join(ROOT, p)) for p, _, _ in found)
        top = ', '.join('%s %d' % kv for kv in by_mod.most_common(6))
        print('%-13s %d  — %s\n%14s%s' % (rule, len(found), why, '', top))
        if verbose:
            for p, i, line in found:
                print('    %s:%d  %s' % (p, i, line[:110]))
    print('файлов просмотрено: %d; итого мест: %d' % (seen, total))
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env bash
# Установка / обновление модулей на стенде 20 без чтения журнала целиком.
# Журнал Odoo при -i/-u — тысячи строк; в разговор (и в токены) идут только
# ERROR/CRITICAL/Traceback с контекстом и итог. Полный журнал остаётся на диске.
#
#   bash tools/odoo_run.sh <база> -u coop_theme,coop_wall
#   bash tools/odoo_run.sh --new <база> -i l10n_ru_doc     # базу создать
#
# Без --new база должна существовать: Odoo на незнакомое имя молча создаёт
# новую базу и рапортует успех (замерено 06.10.2026).
# Код возврата: 0 — модули загружены и ошибок нет, 1 — иначе.

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # rudoo20/
NEW=0
[ "${1:-}" = "--new" ] && { NEW=1; shift; }
DB="${1:?база}"; shift
LOG="${TMPDIR:-/tmp}/odoo_run_${DB}.log"
PSQL="$ROOT/pgsql17/bin/psql.exe"

exists=$(PGPASSWORD=odoo "$PSQL" -h 127.0.0.1 -p 5433 -U odoo -d postgres -tAc \
    "select 1 from pg_database where datname='$DB'" 2>/dev/null)
if [ "$NEW" -eq 0 ] && [ "$exists" != "1" ]; then
    echo "odoo_run: базы $DB нет (или PostgreSQL не отвечает). Новую — с --new."; exit 1
fi
if [ "$NEW" -eq 1 ] && [ "$exists" = "1" ]; then
    echo "odoo_run: база $DB уже есть, --new не нужен."; exit 1
fi

# Синтаксис Python у модулей из -i/-u — до запуска движка: опечатка в тесте
# иначе всплывает через минуту прогона трассировкой загрузчика (20.10 — два
# лишних прогона). Модули ищутся в coop-addons/ и coop-addons/forks/.
mods=""; prev=""
for a in "$@"; do
    case "$prev" in -u|-i) mods="$mods,$a" ;; esac
    case "$a" in -u?*|-i?*) mods="$mods,${a#-?}" ;; --update=*|--init=*) mods="$mods,${a#*=}" ;; esac
    prev="$a"
done
dirs=""
for m in $(echo "$mods" | tr ',' ' '); do
    for d in "$ROOT/coop-addons/$m" "$ROOT/coop-addons/forks/$m"; do
        # Windows-Python путь /d/… не понимает и молча не находит файлов.
        [ -f "$d/__manifest__.py" ] && dirs="$dirs|$(cygpath -m "$d")"
    done
done
if [ -n "$dirs" ]; then
    if ! "$ROOT/venv/Scripts/python.exe" -X utf8 -c '
import ast, pathlib, sys
bad = seen = 0
for d in sys.argv[1].strip("|").split("|"):
    for p in pathlib.Path(d).rglob("*.py"):
        seen += 1
        try:
            ast.parse(p.read_text(encoding="utf-8"), str(p))
        except SyntaxError as e:
            bad += 1
            print("odoo_run: синтаксис %s:%s — %s" % (p, e.lineno, e.msg))
if not seen:  # пустой обход — сломан сам инструмент, а не «всё чисто»
    print("odoo_run: проверка синтаксиса не нашла ни одного .py в", sys.argv[1]); bad = 1
sys.exit(1 if bad else 0)' "$dirs"; then
        echo "odoo_run: движок не запускал — сперва синтаксис."; exit 1
    fi
fi

# Журнал на диск — полный (info): по нему видно, что модули действительно
# загрузились. В разговор из него идёт только выжимка ниже. Odoo журнал
# дописывает — обнуляем, иначе посчитаем строки прошлого запуска.
: > "$LOG"
"$ROOT/venv/Scripts/python.exe" "$ROOT/odoo/odoo-bin" -c "$ROOT/odoo.conf" \
    -d "$DB" --db-filter "^${DB}$" --stop-after-init --no-http \
    --log-level=info --logfile "$LOG" "$@"
rc=$?

# Опечатку в имени модуля Odoo пропускает предупреждением и рапортует успех.
errors=$(grep -cE ' (ERROR|CRITICAL) |^Traceback|invalid module names' "$LOG")
loaded=$(grep -cE 'Modules loaded\.' "$LOG")
echo "odoo_run: база $DB, код $rc, ошибок $errors, «Modules loaded» $loaded, журнал $LOG"
# С --test-enable — итог тестов и имена упавших, без чтения журнала руками.
grep -E 'tests? when loading|of [0-9]+ tests' "$LOG" | sed 's/^.*odoo.tests.result: /odoo_run: тесты — /'
grep -E ' (FAIL|ERROR): Test' "$LOG" | sed 's/^.*: \(FAIL\|ERROR\): /odoo_run: упал — \1 /' | head -10
if [ "$errors" -gt 0 ]; then
    # Первые пять ошибок и первая трассировка — этого хватает для диагноза.
    grep -nE ' (ERROR|CRITICAL) |^Traceback|invalid module names' "$LOG" | cut -c1-300 | head -5
    echo '--- первая трассировка:'
    awk '/^Traceback/{t=1} t{print; n++} n>=25{exit}' "$LOG"
fi
[ "$rc" -eq 0 ] && [ "$errors" -eq 0 ] && [ "$loaded" -gt 0 ]

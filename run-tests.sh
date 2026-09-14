#!/usr/bin/env bash
# Прогон автотестов платформы.
#
#   ./run-tests.sh                    — все модули, у которых есть тесты
#   ./run-tests.sh coop_base          — один модуль
#   ./run-tests.sh coop_base coop_projects
#
# Тесты идут в транзакции и откатываются: база остаётся такой же, какой
# была. Поэтому гонять их можно прямо на рабочем стенде, отдельная база
# не нужна.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"

# Стенд на Windows и боевая на Linux раскладываются по-разному, но обе
# кладут venv и odoo рядом с модулями.
if   [ -x "$ROOT/venv/Scripts/python.exe" ]; then PY="$ROOT/venv/Scripts/python.exe"
elif [ -x "$ROOT/venv/bin/python" ];        then PY="$ROOT/venv/bin/python"
else echo "не нашёл python в $ROOT/venv"; exit 1; fi

if   [ -f "$ROOT/odoo.conf" ];        then CONF="$ROOT/odoo.conf"
elif [ -f "/etc/coop-odoo.conf" ];    then CONF="/etc/coop-odoo.conf"
else echo "не нашёл odoo.conf"; exit 1; fi

DB="${COOP_TEST_DB:-koopeh}"

# Без аргументов — всё, где есть папка tests. Список не держим отдельно:
# он разошёлся бы с действительностью на первом же новом модуле.
if [ $# -gt 0 ]; then
  MODULES="$*"
else
  MODULES="$(cd "$HERE" && ls -d coop_*/tests 2>/dev/null | cut -d/ -f1 | tr '\n' ' ')"
fi
[ -n "${MODULES// /}" ] || { echo "тестов нет ни в одном модуле"; exit 0; }

LIST="$(echo "$MODULES" | tr ' ' ',' | sed 's/,$//')"
TAGS="/$(echo "$MODULES" | sed 's/ *$//' | sed 's/ /,\//g')"

echo "== Модули: $LIST"
echo "== Метки:  $TAGS"

LOG="$(mktemp)"
# MSYS_NO_PATHCONV — иначе Git Bash на Windows превращает «/coop_base» в
# путь «C:/Program Files/Git/coop_base», и Odoo отвергает метку.

# Флаг выключает перевод путей целиком, поэтому остальные аргументы
# надо перевести самим: без этого «/d/dao cooptech/…» уходит в python
# как есть и не открывается.
win() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}

MSYS_NO_PATHCONV=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
  "$PY" "$(win "$ROOT/odoo/odoo-bin")" -c "$(win "$CONF")" -d "$DB" \
  -u "$LIST" --test-enable --test-tags "$TAGS" \
  --stop-after-init --no-http --logfile= > "$LOG" 2>&1

grep -E "odoo\.tests\.(stats|result)" "$LOG" | sed -E 's/^[0-9-]+ [0-9:,]+ [0-9]+ [A-Z]+ [^ ]+ //'

# Подробности — только если что-то упало: иначе вывод тонет в шуме
# загрузчиков наполнения, которые при обновлении отрабатывают заново.
if ! grep -qE "odoo\.tests\.result: 0 failed, 0 error" "$LOG"; then
  echo
  echo "== Что упало"
  grep -E "^(FAIL|ERROR): |AssertionError|odoo\.exceptions\." "$LOG" \
    | grep -v "duplicate key value" | head -40
  echo
  echo "полный журнал: $LOG"
  exit 1
fi
rm -f "$LOG"
echo "== Все тесты прошли"

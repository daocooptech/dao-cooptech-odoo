#!/usr/bin/env python3
"""Открытые задачи vault — в задачи нашего проекта в краудсорсинге.

Решение 690: задачи из полного списка (`Задачи/00 Все задачи`) в
состояниях «в очереди» и «ждёт ответа» выставляются в нашем проекте
«ДАО КООПТЕХ» за токены услуг платформы. Скрипт снимает их с заметок
vault и пишет `coop_bounty/data/cooptech_tasks.json`; модуль при
обновлении заводит новые и обновляет открытые (`_coop_sync_cooptech_tasks`).

    python tools/vault_tasks.py "D:/dao cooptech/ObsidianVault"

Сумма — по размеру задачи: объём заметки и число решений в связке.
Весь список держится в пределах 85 % фонда задач (100 000 токенов),
чтобы новым задачам осталось место.
"""
import json
import re
import sys
from pathlib import Path

OPEN_STATES = ('в очереди', 'ждёт ответа')
FUND_SHARE = 85000
STEPS = (300, 500, 800, 1200, 1600, 2000, 2500)

# Внутренние имена агентов и слова, которых на экране быть не должно
# (решение 684: не «боевая», а «сервер»).
REPLACE = [
    (r'\bcoop-economist\b', 'экономист'),
    (r'\blegal-counsel\b', 'юрист'),
    (r'\baccountant\b', 'бухгалтер'),
    (r'\bfinancier\b', 'финансист'),
    (r'\bproject-manager\b', 'менеджер проекта'),
    (r'\bux-ui-designer\b', 'дизайнер интерфейсов'),
    (r'\bdecentralized-dev\b', 'архитектор'),
    (r'\bmarketer\b', 'маркетолог'),
    (r'на боевой', 'на сервере'),
    (r'боевой', 'сервера'),
    (r'; после остальных выводов [^;.]*', ''),
    (r'`', ''),
]

SPECIALIZATIONS = [
    ('Юрисконсульт', ('юрист', '-фз', 'правов', 'по тексту норм', ' гк', 'закон', 'договор')),
    ('Бухгалтерия', ('бухгалтер', 'adesk', 'упд', 'ндс', 'рсбу', 'баланс организации', 'проводк')),
    ('Переводчик', ('перевод',)),
    ('Фото, видео, звукооператоры', ('ролик', 'видео')),
    ('Дизайн, графика', ('дизайн', 'фото', 'картин', 'значк', 'иконк', 'обрезк')),
    ('Тестирование', ('прогон', 'автотест')),
    ('Бизнес-консультант', ('экономист', 'финмодел', 'финансист', 'инвестор', 'основателю', 'simex')),
    ('Аналитика, Data Science', ('цифры сети', 'калькулятор', 'отчёт', 'аналитик', 'сеть обязательств')),
]
DEFAULT_SPECIALIZATION = 'Программирование, Разработка'


def frontmatter(text):
    match = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not match:
        return {}, text
    data = {}
    for line in match.group(1).splitlines():
        if re.match(r'^[a-z_]+:', line):
            key, _sep, value = line.partition(':')
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data, text[match.end():]


def clean(text):
    for pattern, repl in REPLACE:
        text = re.sub(pattern, repl, text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()


def specialization(text):
    low = text.lower()
    for name, keys in SPECIALIZATIONS:
        if any(key in low for key in keys):
            return name
    return DEFAULT_SPECIALIZATION


def weight(name, size):
    """Размер задачи: объём заметки, связка решений — по их числу."""
    score = size / 1000
    bundle = re.match(r'Решени[яе] (\d+)[–-](\d+)', name)
    if bundle:
        score = max(score, (int(bundle.group(2)) - int(bundle.group(1)) + 1) * 0.6)
    return score


def main(vault):
    rows = []
    for path in sorted(Path(vault, 'Задачи').glob('*.md')):
        data, _body = frontmatter(path.read_text(encoding='utf-8'))
        if data.get('type') != 'task' or data.get('state') not in OPEN_STATES:
            continue
        name = clean(path.stem)
        summary = clean(data.get('summary', ''))
        if summary:
            summary = summary[0].upper() + summary[1:]
            if not summary.endswith('.'):
                summary += '.'
        rows.append({
            'ref': int(data['id']),
            'name': name,
            'summary': summary,
            'waiting': data['state'] == 'ждёт ответа',
            'specialization': specialization(name + ' ' + summary),
            'weight': weight(name, path.stat().st_size),
        })
    # Ступени суммы — по квантилям размера, потом общий масштаб под фонд.
    ordered = sorted(rows, key=lambda row: row['weight'])
    for index, row in enumerate(ordered):
        row['reward'] = STEPS[min(len(STEPS) - 1, index * len(STEPS) // len(ordered))]
    total = sum(row['reward'] for row in rows)
    if total > FUND_SHARE:
        scale = FUND_SHARE / total
        for row in rows:
            row['reward'] = max(100, int(row['reward'] * scale) // 100 * 100)
    for row in rows:
        del row['weight']
    rows.sort(key=lambda row: row['ref'])
    out = Path(__file__).resolve().parent.parent / 'coop_bounty' / 'data' / 'cooptech_tasks.json'
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + '\n', encoding='utf-8',
                   newline='\n')
    print('задач %s, сумма %s, файл %s' % (len(rows), sum(r['reward'] for r in rows), out))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'D:/dao cooptech/ObsidianVault')

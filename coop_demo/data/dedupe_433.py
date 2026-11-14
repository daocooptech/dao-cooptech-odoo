# -*- coding: utf-8 -*-
"""Ресурсы без копий (задача 433, 14.11.2026).

До починки загрузчиков (задача 443) каждая выкатка заводила ещё по одной
копии объявления, а `tidy_names` навешивал копиям хвосты («, срочно,
торг уместен»), и в «Ресурсах» набралось 2230 личных объявлений из 249
разных: «Участок под склад» — 103 копии у одного владельца, «Мотопомпа» —
55 у четырёх. Чистка 443 тронула только три объявления о земле.

Основа объявления — название до первой запятой. Потребности проектов не
трогаем: у них свой учёт копий.

1. В паре (основа, владелец) остаётся самая ранняя запись. Сделки, вклады,
   бартер и заявки на токены с копий переводятся на неё — владелец тот же,
   стороны сделок не меняются.
2. Среди владельцев одной основы остаётся самый ранний; у остальных запись
   остаётся, только если на неё ссылаются сделки, вклады, бартер или
   заявки на токены (это уже другое объявление того же товара).
3. Остальное удаляется; история передач, снимки и условия уходят каскадом.

Повторный прогон ничего не меняет.
"""
import logging

_logger = logging.getLogger(__name__)

# Поля, которые держат объявление: копию не удаляем, а переводим на основную.
REFS = (
    ('coop_deal', 'resource_id'),
    ('coop_project_contribution', 'resource_id'),
    ('coop_barter_offer', 'resource_id'),
    ('coop_token_claim', 'resource_id'),
)

_BASE = """
    SELECT id, split_part(name, ',', 1) AS b, owner_id
      FROM coop_resource
     WHERE NOT coalesce(is_project_need, false)
"""


def _referenced(cr):
    ids = set()
    for table, column in REFS:
        cr.execute(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL')
        ids.update(row[0] for row in cr.fetchall())
    return ids


def relink_same_owner(env):
    """Шаг 1: ссылки с копий одного владельца — на его самую раннюю запись."""
    cr = env.cr
    cr.execute(f"""
        SELECT id, keep FROM (
            SELECT id, min(id) OVER (PARTITION BY b, owner_id) AS keep
              FROM ({_BASE}) r) t
         WHERE id <> keep""")
    pairs = cr.fetchall()
    if not pairs:
        return 0
    moved = 0
    cr.execute('CREATE TEMP TABLE IF NOT EXISTS coop_433_map (src int, dst int)')
    cr.execute('TRUNCATE coop_433_map')
    cr.executemany('INSERT INTO coop_433_map VALUES (%s, %s)', pairs)
    for table, column in REFS:
        cr.execute(f"""
            UPDATE {table} t SET {column} = m.dst
              FROM coop_433_map m WHERE t.{column} = m.src""")
        moved += cr.rowcount
    cr.execute('DROP TABLE coop_433_map')
    env.invalidate_all()
    return moved


def surplus_ids(env):
    """Шаги 2–3: какие объявления лишние."""
    cr = env.cr
    referenced = _referenced(cr)
    cr.execute(f"""
        SELECT id, keep, first FROM (
            SELECT id,
                   min(id) OVER (PARTITION BY b, owner_id) AS keep,
                   min(id) OVER (PARTITION BY b) AS first
              FROM ({_BASE}) r) t""")
    out = []
    for rid, keep, first in cr.fetchall():
        if rid == first:
            continue
        if rid == keep and rid in referenced:
            continue
        out.append(rid)
    return sorted(out)


def dedupe_resources(env):
    moved = relink_same_owner(env)
    ids = surplus_ids(env)
    Resource = env['coop.resource'].sudo().with_context(
        active_test=False, tracking_disable=True, mail_notrack=True)
    removed = kept = 0
    # Пачками: выкатка на боевой ограничена по памяти.
    for start in range(0, len(ids), 100):
        for resource in Resource.browse(ids[start:start + 100]):
            try:
                with env.cr.savepoint():
                    resource.unlink()
                removed += 1
            except Exception as error:  # noqa: BLE001 — держат ссылки
                _logger.warning('Задача 433: объявление %s не удалено (%s)',
                                resource.id, error)
                kept += 1
        env.invalidate_all()
    _logger.info('Задача 433: ссылок перевязано %s, объявлений удалено %s, '
                 'не удалось %s', moved, removed, kept)
    return moved, removed, kept

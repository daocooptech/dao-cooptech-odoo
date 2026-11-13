# -*- coding: utf-8 -*-
"""Чистка копий, которые плодила каждая выкатка (задача 443, 13.11.2026).

Причины устранены в загрузчиках (коммит 8864eb69); здесь — накопленное:

- участники отделов продаж: по одной записи на пару (отдел, человек),
  остаётся активная, а если активной нет — самая ранняя;
- продукты-тёзки одной компании учёта: остаётся самый ранний, объявления
  перепривязываются к его спецификации; копию со спецификацией удаляем,
  а если на неё ссылаются выпуски или строки заказов — убираем в архив;
- три объявления о земле, которые размножились до сотни копий: остаётся
  самое раннее по названию и городу; копию со сделкой не трогаем.

Повторный прогон ничего не меняет.
"""
import logging

_logger = logging.getLogger(__name__)

LAND_BASES = ('Участок под пасеку', 'Ищу участок под теплицы до 20 соток',
              'Обменяю участок 6 соток на инструмент и материалы')


def dedupe_team_members(env):
    env.cr.execute("""
        DELETE FROM crm_team_member m USING (
            SELECT id, row_number() OVER (
                PARTITION BY crm_team_id, user_id ORDER BY active DESC, id) AS rn
            FROM crm_team_member) d
        WHERE m.id = d.id AND d.rn > 1""")
    removed = env.cr.rowcount
    env.invalidate_all()
    return removed


def dedupe_products(env):
    env.cr.execute("""
        SELECT id, first_value(id) OVER w FROM (
            SELECT id, company_id, coalesce(name->>'ru_RU', name->>'en_US') AS n
            FROM product_template) t
        WINDOW w AS (PARTITION BY company_id, n ORDER BY id)""")
    copies = {tid: keep for tid, keep in env.cr.fetchall() if tid != keep}
    Template = env['product.template'].sudo().with_context(active_test=False)
    Bom = env['mrp.bom'].sudo().with_context(active_test=False)
    Resource = env['coop.resource'].sudo().with_context(active_test=False)
    removed = archived = relinked = 0
    for tid, keep in sorted(copies.items()):
        copy = Template.browse(tid)
        boms = Bom.search([('product_tmpl_id', '=', tid)])
        main = Bom.search([('product_tmpl_id', '=', keep)], order='id', limit=1)
        if boms and main:
            linked = Resource.search([('bom_id', 'in', boms.ids)])
            if linked:
                linked.write({'bom_id': main.id})
                relinked += len(linked)
        try:
            with env.cr.savepoint():
                boms.unlink()
                copy.unlink()
            removed += 1
        except Exception as error:  # noqa: BLE001 — ссылки держат: в архив
            _logger.info('Задача 443: продукт %s в архив (%s)', tid, error)
            boms.write({'active': False})
            copy.write({'active': False})
            archived += 1
    return removed, archived, relinked


def dedupe_land(env):
    env.cr.execute("""
        SELECT r.id FROM (
            SELECT r.id, row_number() OVER (
                PARTITION BY split_part(r.name, ',', 1), r.city ORDER BY r.id) AS rn
            FROM coop_resource r
            JOIN coop_resource_category c ON c.id = r.category_id
            WHERE c.name = 'Земельные участки'
              AND split_part(r.name, ',', 1) IN %s) r
        WHERE r.rn > 1
          AND NOT EXISTS (SELECT 1 FROM coop_deal d WHERE d.resource_id = r.id)""",
                   [LAND_BASES])
    ids = [row[0] for row in env.cr.fetchall()]
    Resource = env['coop.resource'].sudo().with_context(active_test=False)
    removed = kept = 0
    for resource in Resource.browse(ids):
        try:
            with env.cr.savepoint():
                resource.unlink()
            removed += 1
        except Exception as error:  # noqa: BLE001
            _logger.warning('Задача 443: объявление %s не удалено (%s)', resource.id, error)
            kept += 1
    return removed, kept


def dedupe_all(env):
    members = dedupe_team_members(env)
    products = dedupe_products(env)
    land = dedupe_land(env)
    _logger.info('Задача 443: участников отделов убрано %s; продуктов удалено %s, '
                 'в архив %s, объявлений перепривязано %s; объявлений о земле '
                 'удалено %s, не удалось %s',
                 members, products[0], products[1], products[2], land[0], land[1])
    return members, products, land

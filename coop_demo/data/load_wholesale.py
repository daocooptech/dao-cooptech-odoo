# -*- coding: utf-8 -*-
"""Опт и розница в демо (задача 401, решение 634). Идемпотентно.

У четверти объявлений с ценой продажи — наименьшая партия и от одной до
трёх ступеней «от N — цена»; единицы измерения разные, а не одно «шт.».
Выбор детерминирован номером записи: повторный прогон ничего не меняет, а
уже заполненные продавцом ступени не трогаем.
"""

# Единицы по смыслу рубрики не подбираем: демо-набор — разброс, не учёт.
UNITS = ['шт.', 'шт.', 'кг', 'т', 'м²', 'м³', 'комплект', 'упаковка', 'паллета',
         'рулон', 'мешок', 'л', 'пара', 'коробка', 'м']
BATCHES = [5, 10, 20, 50, 100]
# Скидка ступени к цене: первая, вторая, третья.
DISCOUNTS = [0.93, 0.88, 0.82]


def _money(value):
    """Цена ступени: до тысячи — до рубля, дальше — до десяти рублей."""
    return float(round(value) if value < 1000 else round(value / 10.0) * 10)


def load_wholesale(env):
    Term = env['coop.resource.term'].sudo().with_context(
        tracking_disable=True, coop_no_price_sync=True)
    terms = Term.search([('code', '=', 'sale'), ('price', '>', 0),
                         ('price_kind', '!=', 'none')], order='id')
    made = 0
    for term in terms:
        vals = {}
        if not term.price_unit_label:
            vals['price_unit_label'] = UNITS[term.id % len(UNITS)]
        if term.bulk_qty or term.bulk2_qty or term.bulk3_qty:
            if vals:
                term.write(vals)
            continue
        # Четверть записей: 1 из 4 по номеру.
        if term.id % 4:
            if vals:
                term.write(vals)
            continue
        steps = 1 + (term.id // 4) % 3
        base = term.min_qty or BATCHES[(term.id // 12) % len(BATCHES)]
        vals['min_qty'] = base
        qty = base
        previous = term.price
        for number in range(steps):
            qty = qty * 2
            price = _money(term.price * DISCOUNTS[number])
            if price <= 0 or price >= previous:
                break      # дешевле не получается — ступень не нужна
            suffix = '' if number == 0 else str(number + 1)
            vals['bulk%s_qty' % suffix] = float(qty)
            vals['bulk%s_price' % suffix] = price
            previous = price
        if 'bulk_qty' not in vals:
            if term.price_unit_label or 'price_unit_label' in vals:
                term.write({k: v for k, v in vals.items() if k == 'price_unit_label'})
            continue
        term.write(vals)
        made += 1
    # Хранимые поля объявления (`has_wholesale`, `min_batch`, цена)
    # пересчитываются по записи условий; добиваем тем, где запись шла
    # мимо зависимостей.
    resources = terms.mapped('resource_id')
    env.add_to_compute(resources._fields['has_wholesale'], resources)
    resources.flush_recordset(['has_wholesale', 'min_batch', 'wholesale_price'])
    return made

# -*- coding: utf-8 -*-
"""Единый справочник специализаций.

Собран разбором четырёх файлов прототипа — `people.html`,
`organizations.html`, `vacancies.html` и `skills.html`. Дерево одно на все
каталоги по решению владельца от 2026-09-01, и разбор показал, что это
возможно без противоречий: ни одна специализация не встречается в двух
сферах деятельности сразу.

Ресурсы сюда не входят намеренно. Под теми же атрибутами макета у них
лежит дерево товарных категорий — Недвижимость, Транспорт, Электроника,
Продовольственные товары. Это вид товара, а не специализация исполнителя,
и сводить одно с другим значит получить справочник, в котором «Сварщик» и
«Ноутбуки и компьютеры» стоят рядом как однородные записи. Ресурсам место
в product.category.
"""
import json
import logging
import os

_logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))


def load_specializations(env):
    with open(os.path.join(HERE, 'specializations.json'), encoding='utf-8') as fh:
        tree = json.load(fh)

    Category = env['coop.specialization.category']
    Specialization = env['coop.specialization']

    categories, specializations = {}, {}
    for category_name, names in tree.items():
        category = Category.search([('name', '=', category_name)], limit=1)
        if not category:
            category = Category.create({'name': category_name})
        categories[category_name] = category

        for name in names:
            record = Specialization.search([('name', '=', name)], limit=1)
            if record:
                # Сфера могла измениться в макете — переносим, а не
                # заводим вторую запись с тем же названием.
                if record.category_id != category:
                    record.category_id = category.id
            else:
                record = Specialization.create(
                    {'name': name, 'category_id': category.id})
            specializations[name] = record

    _logger.info('Справочник специализаций: %s сфер, %s специализаций',
                 len(categories), len(specializations))
    return categories, specializations

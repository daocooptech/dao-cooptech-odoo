# -*- coding: utf-8 -*-
"""Девять разделов материальных ресурсов (задача 396, решение 632).

Лежит у `coop_attributes`, а не у `coop_resources`: у перестройки есть
привязки характеристик к категориям, а их модель появляется в реестре
только вместе с этим модулем. Саму перестройку — переименование и переезд
категорий на месте, перенос записей по названию — делает функция
`coop_resources.models.coop_resource_tree.rebuild_category_tree`.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.coop_resources.models.coop_resource_tree import (
    rebuild_category_tree)


def migrate(cr, version):
    if not version:
        return
    rebuild_category_tree(api.Environment(cr, SUPERUSER_ID, {}))

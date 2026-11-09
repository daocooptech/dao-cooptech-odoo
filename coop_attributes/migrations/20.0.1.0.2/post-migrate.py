# -*- coding: utf-8 -*-
"""Дерево по образцу досок объявлений (задача 398, утверждено 10.11.2026).

Недвижимость — жилая и коммерческая, у техники свои виды, «Прочее
оборудование» и объявления без раздела расходятся по названию. Делает
та же идемпотентная `rebuild_category_tree` — к ней добавлен шаг
`rebuild_398`.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.coop_resources.models.coop_resource_tree import (
    rebuild_category_tree)


def migrate(cr, version):
    if not version:
        return
    rebuild_category_tree(api.Environment(cr, SUPERUSER_ID, {}))

# -*- coding: utf-8 -*-
"""Условия демо-объявлений — под проверки публикации (решение 629).

Разборы агентов 27.10.2026: у рассрочки — срок и периодичность, у лизинга
«я сам» — продавец, у аренды с оператором — транспорт или нет, у вклада в
пользование — срок, ставка, ремонт, износ, утрата, у продажи организации —
документы и НДС, у дара организациям и мены организации — оценка.
Заполняются только пустые поля.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.coop_demo.data import load_resource_terms


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    load_resource_terms.fill_term_checks(env)

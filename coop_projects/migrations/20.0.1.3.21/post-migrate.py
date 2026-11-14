# -*- coding: utf-8 -*-
"""Город — всем проектам «Управления проектами» (владелец 14.11.2026:
«назначь города всем проектам»).

Порядок источников: город в названии («… — Казань»), город сбора или
заказчика (уже посчитан полем), иначе — город из списка платформы по
номеру проекта, чтобы разброс был ровным и повторялся от прогона к
прогону.
"""
from odoo import SUPERUSER_ID, api

CITIES = ['Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань',
          'Нижний Новгород', 'Самара', 'Тюмень', 'Пермь', 'Красноярск', 'Омск',
          'Уфа', 'Воронеж', 'Краснодар', 'Ярославль', 'Вологда', 'Хабаровск',
          'Владивосток', 'Калининград', 'Тобольск', 'Ишим', 'Архангельск',
          'Челябинск', 'Ростов-на-Дону', 'Иркутск', 'Псков', 'Тула', 'Курск',
          'Волгоград', 'Сочи', 'Кемерово', 'Магнитогорск', 'Нижний Тагил']


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'lang': 'ru_RU'})
    projects = env['project.project'].with_context(active_test=False).search([])
    for project in projects:
        tail = (project.name or '').rsplit(' — ', 1)
        named = tail[1].strip() if len(tail) == 2 else ''
        if named in CITIES:
            city = named
        else:
            city = project.city or CITIES[project.id % len(CITIES)]
        if project.city != city:
            project.city = city
    env.flush_all()

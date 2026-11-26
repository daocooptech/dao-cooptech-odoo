# -*- coding: utf-8 -*-
"""Решение 510: подряд — не вакансией, а задачей с результатом.

Договор подряда и способы выплаты «остаток в пай» и «токенами» уходят из
вакансии, и движок при обновлении обнулит эти значения. Пока они целы —
запоминаем подрядные вакансии вместе со способом выплаты: их переносит в
задачи миграция coop_demo, у которой есть модуль задач.
"""


def migrate(cr, version):
    cr.execute("""
        CREATE TABLE IF NOT EXISTS coop_vacancy_to_task_510 (
            vacancy_id integer PRIMARY KEY,
            pay_method varchar
        )""")
    cr.execute("""
        INSERT INTO coop_vacancy_to_task_510 (vacancy_id, pay_method)
        SELECT id, pay_method FROM coop_vacancy WHERE contract_kind = 'civil'
        ON CONFLICT DO NOTHING""")

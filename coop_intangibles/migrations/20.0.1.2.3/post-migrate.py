# -*- coding: utf-8 -*-
"""«Нужно» — сумма всех четырёх списков потребностей (решение 652, 11.11.2026).

Поле `required_total` было вписываемым, стало вычисляемым: старые значения
движок сам не пересчитает. Пересчёт здесь, а не в `coop_projects`: к этому
моменту загружена и надстройка нематериальных, без неё в сумму не попали
бы строки НМА.

Перед пересчётом — чистка демо: загрузчик нематериальных потребностей
добавлял строки при каждом обновлении (до 62 на проект). `coop_demo` от
этого модуля не зависит, и его миграция могла бы пройти раньше, чем
появится модель, — поэтому чистка вызывается отсюда.

Демо-вклады строились под прежнее «Нужно» и готовность из макета; они
масштабируются той же пропорцией, что и «Нужно», — готовность остаётся
прежней, а не уходит за сотни процентов. Прежнее «Нужно» читается из
базы до чистки: правка строк сама пересчитывает поле и стирает его.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'tracking_disable': True})
    cr.execute('SELECT id, required_total FROM coop_project')
    before = {pid: float(value or 0.0) for pid, value in cr.fetchall()}

    demo = env['ir.module.module'].search(
        [('name', '=', 'coop_demo'), ('state', 'in', ('installed', 'to upgrade'))])
    if demo:
        from odoo.addons.coop_demo.data import load_intangible_needs
        load_intangible_needs.shrink_intangible_needs(env)

    # Запись напрямую: пометка «пересчитать» (`add_to_compute`) на стенде
    # 11.11 не сработала — у 90 проектов из 146 осталось старое «Нужно».
    fixed = scaled = 0
    projects = env['coop.project'].with_context(active_test=False).search([])
    for project in projects:
        total = project._coop_needs_total()
        if not total:
            continue
        old = before.get(project.id) or 0.0
        if demo and old and abs(total - old) >= 0.01:
            for contribution in project.contribution_ids:
                contribution.value = round(contribution.value * total / old)
            scaled += 1
        if abs(total - project.required_total) >= 0.01:
            project.required_total = total
            fixed += 1
    _logger.info('«Нужно» пересчитано у %d проектов из %d, вклады '
                 'масштабированы у %d', fixed, len(projects), scaled)

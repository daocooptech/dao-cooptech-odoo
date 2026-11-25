# -*- coding: utf-8 -*-
"""Имя и форма собственности фонда (владелец 26.11.2026)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    project = env['coop.project'].search(
        [('name', '=', 'Ретроактивный фонд открытого кода')])
    if not project:
        return
    values = {'name': 'Фонд развития проектов с открытым исходным кодом'}
    models = env['coop.economic.model'].search(
        [('legal_form_id.code', '=', 'fond')], order='id')
    # Налоговый режим остаётся прежним, меняется только форма.
    tax = (project[0].economic_model_id.name or '').partition(' на ')[2]
    model = models.filtered(lambda m: tax and m.name.endswith(' на ' + tax))[:1] or models[:1]
    if model:
        values['economic_model_id'] = model.id
    project.write(values)

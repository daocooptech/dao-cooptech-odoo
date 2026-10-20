"""Счёт 000 «Вспомогательный» — во все планы (загрузка пропускает имеющиеся)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Wizard = env['rsbu.account.load.wizard']
    for company in env['res.company'].search([]):
        Wizard.create({'company_id': company.id}).action_load()

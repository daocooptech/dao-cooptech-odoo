# -*- coding: utf-8 -*-
"""«Закупки» — приложение организации, как CRM (владелец 20.10.2026).

Включаются по набору правовых форм (коммерческие, в том числе ИП и КФХ,
и кооперативы) у организаций с компанией учёта; людям с полномочием
«Сделки» или «Казна» доступ выдаётся по общей раздаче. Однократно, при
переходе на эту версию: повторный проход затирал бы выбор руководителя.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orgs = env['res.partner'].with_context(active_test=False).search([
        ('is_company', '=', True),
        ('coop_legal_form_group_id.code', 'in', ('commercial', 'cooperative'))])
    orgs.write({'coop_app_purchase': True})
    _logger.info('«Закупки» включены у %s организаций', len(orgs))

# -*- coding: utf-8 -*-
"""Уведомления людей платформы — во «Входящие» (владелец 15.11.2026).

Новым пользователям группа «Входящие» приходит через «Пользователя»
(`data/coop_notification_data.xml`), а у нынешних хранимое
`notification_type` от смены подразумеваемых групп само не
пересчитывается — ставим явно; обратная запись движка добавит группу.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    users = env['res.users'].with_context(active_test=False).search([
        ('share', '=', False), ('notification_type', '!=', 'inbox'),
    ])
    users.write({'notification_type': 'inbox'})

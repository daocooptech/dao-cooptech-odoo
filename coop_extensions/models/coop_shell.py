# -*- coding: utf-8 -*-
from odoo import api, models


class CoopShell(models.AbstractModel):
    _inherit = 'coop.shell'

    @api.model
    def boot(self):
        """«Настроить меню» от имени организации — только порядок разделов.

        Расширения организации подключают и убирают в каталоге, а кому они
        открыты — во вкладке «Права доступа» (решение 481 п. 5; экрана
        «Меню организации» больше нет). Личные расширения от имени
        организации не показываются: руководитель правил бы своё меню и
        не понимал, почему у коллег ничего не поменялось.
        """
        data = super().boot()
        user = self.env.user
        org = user.coop_acting_as_id
        if org and org != user.partner_id:
            action = self.env.ref('coop_extensions.action_coop_sidebar_sections',
                                  raise_if_not_found=False)
            data['menuSettings'] = action.id if action else False
        return data

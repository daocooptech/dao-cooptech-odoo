# -*- coding: utf-8 -*-
from odoo import api, models


class CoopShell(models.AbstractModel):
    _inherit = 'coop.shell'

    @api.model
    def boot(self):
        """«Настроить меню» от имени организации ведёт в меню организации.

        Иначе руководитель, действуя от организации, правил бы своё личное
        меню и не понимал, почему у коллег ничего не поменялось.
        """
        data = super().boot()
        user = self.env.user
        org = user.coop_acting_as_id
        if org and org != user.partner_id:
            action = self.env.ref('coop_extensions.action_coop_org_menu',
                                  raise_if_not_found=False)
            data['menuSettings'] = action.id if action else False
        return data

# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Первый вход участника не из России — сперва валюта (решение 482).

        Пока валюта не выбрана, домашним экраном вместо «Моей страницы»
        открывается «Язык и регион». Выбрал — дальше всё как у всех; у
        граждан и организаций России выбора нет, им ничего не подменяется.
        """
        info = super().session_info()
        user = self.env.user
        partner = user.partner_id
        if (user and not user.share and partner
                and not partner._coop_rub_only()
                and not partner.coop_currency_id):
            region = self.env.ref('coop_settings.action_coop_settings_region',
                                  raise_if_not_found=False)
            if region:
                info['home_action_id'] = region.id
        return info

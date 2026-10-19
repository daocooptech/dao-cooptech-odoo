# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.tools.binary import BinaryBytes
from odoo.tools.misc import file_open


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _coop_team_logo(self):
        """Знак у «Рабочей группы платформы» (владелец 12.10.2026): лого coop,
        как в шапке, и «team» под ним — вместо серой заглушки.

        Рабочая группа — партнёр служебной учётной записи движка
        (`base.partner_admin`, решение 126). Картинку ставим, только пока
        своей нет: заменённую руками обновление не перетирает.
        """
        partner = self.env.ref('base.partner_admin', raise_if_not_found=False)
        if not partner or partner.sudo().image_1920:
            return False
        with file_open('coop_theme/static/src/img/team-logo.png', 'rb') as handle:
            # Движок 20 пишет двоичные поля сырыми байтами в BinaryBytes,
            # а не base64: строка base64 падает TypeError при обновлении.
            partner.sudo().image_1920 = BinaryBytes(handle.read())
        return True

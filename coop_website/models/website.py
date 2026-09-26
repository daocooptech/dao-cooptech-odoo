# -*- coding: utf-8 -*-
from odoo import api, models


class Website(models.Model):
    _inherit = 'website'

    @api.model
    def _coop_default_lang_ru(self):
        """Решение 420: сайт — на русском по умолчанию, английский — вторым.

        Функцией, а не записью в данных: запись сайта у модуля `website`
        помечена `noupdate`, и чужие данные её при обновлении не меняют.
        """
        ru = self.env.ref('base.lang_ru', raise_if_not_found=False)
        en = self.env.ref('base.lang_en', raise_if_not_found=False)
        if not ru or not ru.active:
            return False
        for website in self.sudo().search([]):
            website.language_ids = [(4, ru.id)] + ([(4, en.id)] if en and en.active else [])
            website.default_lang_id = ru.id
        return True

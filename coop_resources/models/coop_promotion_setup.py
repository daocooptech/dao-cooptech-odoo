# -*- coding: utf-8 -*-
from odoo import api, models

from ..data import coop_promotion_slots


class CoopPromotionSetup(models.AbstractModel):
    """Заведение мест в выдаче.

    Кодом, а не двадцатью XML-записями: цена и охват считаются по
    формуле, и держать их списком значит вручную пересчитывать двадцать
    чисел всякий раз, когда меняется затухание внимания или цена первой
    строки.
    """
    _name = 'coop.promotion.setup'
    _description = 'Настройка мест в выдаче'

    @api.model
    def apply(self):
        return coop_promotion_slots.load_promotion_slots(self.env)

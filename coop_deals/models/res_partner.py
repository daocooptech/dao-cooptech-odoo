# -*- coding: utf-8 -*-
"""Счётчики сделок и отзывов у участника.

Поля `coop_deals_done` и `coop_deals_rated` заведены в `coop_base` рядом
с уровнем доверия, но их никто не считал: числа приходили из
демонстрационных данных и с действительностью не сверялись. Человек с
сорока завершёнными сделками мог показывать три, а мог и наоборот.

Считаем здесь, а не в `coop_base`: сделка живёт в этом модуле, и
базовому знать о ней незачем.

Пересчёт по событию, а не вычисляемым полем с зависимостями: зависеть
пришлось бы от таблицы, где участник встречается двумя разными полями и
где считать нужно обе стороны сразу, — Odoo такую зависимость через
`@api.depends` не выражает. Событий всего два: сделка стала завершённой и
появился отзыв.
"""

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _coop_recompute_deal_stats(self):
        """Пересчитать завершённые сделки и отзывы о человеке."""
        Deal = self.env['coop.deal'].sudo()
        Review = self.env['coop.deal.review'].sudo()
        for partner in self:
            partner.coop_deals_done = Deal.search_count([
                ('state', '=', 'done'),
                '|', ('party_a_id', '=', partner.id),
                ('party_b_id', '=', partner.id),
            ])
            # Считаем отзывы о человеке, а не сделки с отзывом: у сделки
            # их два, и каждый относится к своей стороне.
            partner.coop_deals_rated = Review.search_count([
                ('target_id', '=', partner.id),
            ])
        return True

    @api.model
    def _coop_recompute_all_deal_stats(self):
        """Разовый пересчёт по всем — для переноса и после загрузки данных."""
        участники = self.sudo().search([])
        участники._coop_recompute_deal_stats()
        return len(участники)

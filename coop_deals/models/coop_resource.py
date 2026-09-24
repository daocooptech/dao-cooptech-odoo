# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class CoopResource(models.Model):
    """Покупатели ресурса — со страницы самого ресурса.

    В дизайн-макете у карточки ресурса был блок «Покупатели» с отбором
    (решения 10, 14 и 16 журнала владельца). На движке данные были —
    сделка знает свой ресурс (`coop.deal.resource_id`), — а со страницы
    ресурса к ним не вело ничего: ни числа, ни перехода. Ревизия макета и
    MVP 22 сентября 2026 записала это расхождением.

    Живёт здесь, а не в `coop_resources`: сделки зависят от ресурсов, а не
    наоборот, и ресурс о сделках знать не должен.
    """
    _inherit = 'coop.resource'

    coop_buyer_count = fields.Integer(
        string='Покупатели', compute='_compute_coop_buyer_count')

    @api.depends('owner_id')
    def _compute_coop_buyer_count(self):
        # Покупатель — вторая сторона сделки по этому ресурсу, то есть
        # любая сторона, кроме хозяина объявления. Считаем людей, а не
        # сделки: один покупатель, купивший трижды, — один покупатель.
        Deal = self.env['coop.deal'].sudo()
        groups = Deal._read_group(
            [('resource_id', 'in', self.ids)],
            ['resource_id', 'party_a_id', 'party_b_id'])
        buyers = {}
        for resource, party_a, party_b in groups:
            for party in (party_a, party_b):
                if party:
                    buyers.setdefault(resource.id, set()).add(party.id)
        for resource in self:
            parties = buyers.get(resource.id, set())
            parties.discard(resource.owner_id.id)
            resource.coop_buyer_count = len(parties)

    def action_coop_buyers(self):
        """Сделки по ресурсу — в обычном каталоге сделок, с его отборами.

        Отдельного экрана «Покупатели» не заводим: каталог сделок уже
        умеет искать, отбирать по состоянию и городу и группировать, а
        второй экран с тем же содержимым разошёлся бы с ним при первой же
        правке.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Покупатели: %(name)s', name=self.name),
            'res_model': 'coop.deal',
            'view_mode': 'list,kanban,form',
            'domain': [('resource_id', '=', self.id)],
            'context': {'create': False},
        }

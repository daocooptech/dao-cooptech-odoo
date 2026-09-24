# -*- coding: utf-8 -*-
from odoo import _, fields, models


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

    def _compute_coop_buyer_count(self):
        # Покупатель — вторая сторона сделки (`party_b_id`): так сделка
        # сама раскладывает роли — «покупатель, арендатор, заказчик»
        # (подсказка у `role_b`). Считаем людей, а не сделки: один
        # покупатель, купивший трижды, — один покупатель.
        #
        # Раньше считались обе стороны за вычетом хозяина объявления, и
        # у сварочного полуавтомата с семью сделками выходило четырнадцать
        # покупателей: продавцом в сделке бывает не хозяин объявления.
        # Без обхода прав: число должно совпадать с тем, что человек увидит,
        # перейдя по ссылке. Сделка видна только её сторонам, и со счётом
        # в обход прав выходило «Покупатели: 7» при одной сделке в списке.
        groups = self.env['coop.deal']._read_group(
            [('resource_id', 'in', self.ids), ('party_b_id', '!=', False)],
            ['resource_id'], ['party_b_id:count_distinct'])
        counts = {resource.id: count for resource, count in groups}
        for resource in self:
            resource.coop_buyer_count = counts.get(resource.id, 0)

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

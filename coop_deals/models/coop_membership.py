# -*- coding: utf-8 -*-
from odoo import models


class CoopMembership(models.Model):
    _inherit = 'coop.membership'

    def write(self, vals):
        """Перестал вести сделки организации — сделки ждут нового ответственного.

        Выход из организации или снятое полномочие «Сделки»: ответственным
        по её сделкам человек больше быть не может (решение 450).
        """
        watch = {'state', 'power_ids'} & set(vals)
        before = {m.id: m.state == 'active' and 'deal' in m.power_ids.mapped('code')
                  for m in self} if watch else {}
        result = super().write(vals)
        if watch:
            Deal = self.env['coop.deal']
            for membership in self:
                still = membership.state == 'active' \
                    and 'deal' in membership.power_ids.mapped('code')
                if before.get(membership.id) and not still:
                    for user in membership.partner_id.user_ids:
                        Deal._coop_release_responsible(
                            user, membership.organization_id)
        return result

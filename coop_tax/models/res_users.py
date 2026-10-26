# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Решение 517: пайщик видит лимит кооперативных выплат своего
    # кооператива — от него зависит, сколько начислят ему.
    coop_share_cooperative_ids = fields.Many2many(
        'res.partner', string='Кооперативы, где есть пай',
        compute='_compute_coop_share_cooperative_ids')

    @api.depends('partner_id')
    def _compute_coop_share_cooperative_ids(self):
        Account = self.env['coop.share.account'].sudo()
        for user in self:
            user.coop_share_cooperative_ids = Account.search(
                [('partner_id', '=', user.partner_id.id)]).mapped('cooperative_id')

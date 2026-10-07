# -*- coding: utf-8 -*-
"""«Моя страница» как рабочий стол (решение 450, «как в Битрикс24»).

Кроме витрины человека — две полосы только для него самого: дела на
сегодня и просроченные, и сделки, где следующий ход за ним. Чужим эти
полосы не видны: это не владения, а его работа.
"""
from odoo import _, api, fields, models

SHOW = 8


class ResPartner(models.Model):
    _inherit = 'res.partner'

    coop_my_activity_ids = fields.Many2many(
        'mail.activity', string='Мои дела', compute='_compute_coop_my_day')
    coop_my_activity_count = fields.Integer(compute='_compute_coop_my_day')
    coop_waiting_deal_ids = fields.Many2many(
        'coop.deal', string='Ждут меня', compute='_compute_coop_my_day')
    coop_waiting_deal_count = fields.Integer(compute='_compute_coop_my_day')

    def _coop_my_activities(self):
        """Мои дела со сроком сегодня и раньше — по всем разделам."""
        return self.env['mail.activity'].search([
            ('user_id', '=', self.env.uid),
            ('date_deadline', '<=', fields.Date.context_today(self)),
        ], order='date_deadline, id')

    def _coop_waiting_deals(self):
        """Сделки, где следующий ход за мной как ответственным стороны.

        Обращение от второй стороны ждёт ответа; акт подтвердила вторая
        сторона, а моя нет; срок платежа мне прошёл, а получение не
        отмечено.
        """
        uid = self.env.uid
        mine = self.env.user.coop_actor_partner_ids
        today = fields.Date.context_today(self)
        deals = self.env['coop.deal'].search([
            ('state', 'in', ('lead', 'acceptance', 'agreed', 'active')),
            '|', ('responsible_a_id', '=', uid), ('responsible_b_id', '=', uid),
        ], order='write_date desc, id desc')
        waiting = deals.browse()
        for deal in deals:
            side = 'a' if deal.responsible_a_id.id == uid else 'b'
            party = deal['party_%s_id' % side]
            if deal.state == 'lead' and deal.author_id not in mine:
                waiting |= deal
            elif deal.state == 'acceptance' and not deal['act_confirmed_%s' % side]:
                waiting |= deal
            elif deal.payment_ids.filtered(
                    lambda p: p.state in ('planned', 'overdue')
                    and p.payee_id == party and p.due_on and p.due_on <= today):
                waiting |= deal
        return waiting

    @api.depends_context('uid')
    def _compute_coop_my_day(self):
        me = self.env.user.partner_id
        for record in self:
            if record != me:
                record.coop_my_activity_ids = False
                record.coop_my_activity_count = 0
                record.coop_waiting_deal_ids = False
                record.coop_waiting_deal_count = 0
                continue
            activities = record._coop_my_activities()
            deals = record._coop_waiting_deals()
            record.coop_my_activity_ids = activities[:SHOW]
            record.coop_my_activity_count = len(activities)
            record.coop_waiting_deal_ids = deals[:SHOW]
            record.coop_waiting_deal_count = len(deals)

    def action_coop_my_activities(self):
        """Все мои дела на сегодня и просроченные."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Мои дела'),
            'res_model': 'mail.activity',
            'view_mode': 'list',
            'views': [(self.env.ref('mail.mail_activity_view_tree').id, 'list')],
            'domain': [('id', 'in', self._coop_my_activities().ids)],
            'target': 'current',
        }

    def action_coop_waiting_deals(self):
        """Все сделки, где ход за мной."""
        action = self.env['ir.actions.act_window']._for_xml_id(
            'coop_deals.action_coop_deals')
        action.update({
            'name': _('Ждут меня'),
            'domain': [('id', 'in', self._coop_waiting_deals().ids)],
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
        })
        return action

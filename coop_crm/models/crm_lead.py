from odoo import _, fields, models
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    coop_deal_id = fields.Many2one(
        'coop.deal', string='Сделка площадки', readonly=True, copy=False, index=True)
    coop_import_key = fields.Char(string='Ключ источника', index=True, copy=False)

    def _coop_org(self):
        """Организация, чей это лид: владелец компании учёта."""
        self.ensure_one()
        partner = self.company_id.partner_id
        return partner if partner.coop_company_id == self.company_id else partner.browse()

    def action_coop_create_deal(self):
        """Лид -> сделка площадки (решение 450, «как в Битрикс24»).

        Сделку заводит сам человек, своими правами: она появится у него и
        у клиента в «Сделках», с ним как оформившим. Лид отмечается
        выигранным и помнит свою сделку, сделка — свой лид.
        """
        self.ensure_one()
        if self.coop_deal_id:
            return self.coop_deal_id._coop_form_action()
        org = self._coop_org()
        if not org:
            raise UserError(_('Этот лид не принадлежит организации площадки.'))
        if org not in self.env['res.users']._coop_deal_orgs(self.env.user):
            raise UserError(_(
                'Создать сделку от имени «%s» может только тот, у кого есть '
                'полномочие «Сделки».') % org.name)
        client = self.partner_id.commercial_partner_id
        if not client:
            raise UserError(_('Укажите клиента: с кем будет сделка.'))
        if client == org:
            raise UserError(_('Клиент совпадает с самой организацией.'))
        deal = self.env['coop.deal'].create({
            'name': self.name,
            'way': 'sale',
            'party_a_id': org.id,
            'party_b_id': client.id,
            'role_a': 'Продавец',
            'role_b': 'Покупатель',
            'amount': self.expected_revenue,
            'currency_id': (self.company_currency or org.coop_company_id.currency_id).id,
            'city': self.city or org.city,
            'coop_lead_id': self.id,
        })
        self.coop_deal_id = deal
        self.action_set_won()
        self.message_post(body=_('Создана сделка площадки %s.') % deal.display_name)
        return deal._coop_form_action()

    def action_coop_open_deal(self):
        self.ensure_one()
        return self.coop_deal_id._coop_form_action()

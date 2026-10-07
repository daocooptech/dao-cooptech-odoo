from odoo import fields, models


class CoopDeal(models.Model):
    _inherit = 'coop.deal'

    # Откуда сделка пришла: лид CRM организации. Сделка видна обеим
    # сторонам, а лид — только отделу продаж продавца, поэтому ссылку
    # открывает только тот, у кого есть права на лид.
    coop_lead_id = fields.Many2one(
        'crm.lead', string='Лид', readonly=True, copy=False, index=True)

    def _coop_form_action(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'coop.deal',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_coop_open_lead(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.coop_lead_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

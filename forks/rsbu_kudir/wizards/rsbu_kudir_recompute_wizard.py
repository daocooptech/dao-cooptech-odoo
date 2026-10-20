from odoo import fields, models, _


class RsbuKudirRecomputeWizard(models.TransientModel):
    """Визард пересчёта КУДиР за период."""
    _name = 'rsbu.kudir.recompute.wizard'
    _description = 'РСБУ — Пересчёт КУДиР'

    date_from = fields.Date(string='Дата с', required=True)
    date_to = fields.Date(string='Дата по', required=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True,
        default=lambda self: self.env.company)

    def action_recompute(self):
        self.ensure_one()
        self.env['rsbu.kudir.line'].recompute_period(
            self.date_from, self.date_to, self.company_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('КУДиР'),
            'res_model': 'rsbu.kudir.line',
            'view_mode': 'list',
            'domain': [
                ('company_id', '=', self.company_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ],
        }

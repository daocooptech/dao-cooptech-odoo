from odoo import fields, models, _


class RsbuVatRecomputeWizard(models.TransientModel):
    """Визард пересчёта книг НДС и итогов за период."""
    _name = 'rsbu.vat.recompute.wizard'
    _description = 'РСБУ — Пересчёт книг НДС'

    date_from = fields.Date(string='Дата с', required=True)
    date_to = fields.Date(string='Дата по', required=True)
    company_id = fields.Many2one(
        'res.company', string='Компания', required=True,
        default=lambda self: self.env.company)

    def action_recompute(self):
        self.ensure_one()
        self.env['rsbu.vat.book.line'].recompute_period(
            self.date_from, self.date_to, self.company_id)
        self.env['rsbu.vat.summary'].recompute_period(
            self.date_from, self.date_to, self.company_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Книги НДС'),
            'res_model': 'rsbu.vat.book.line',
            'view_mode': 'list',
            'domain': [
                ('company_id', '=', self.company_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ],
        }

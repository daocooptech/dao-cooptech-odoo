from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .coop_vat_regime import VAT_REGIMES


class CoopRsbuStart(models.TransientModel):
    """«Начать учёт в РСБУ» — у действующей организации (решение 472).

    Новые компании учёта получают слой с рождения; организации, у которых
    компания уже есть, включают его сами: тот, у кого полномочие
    «Бухгалтерия и счета», выбирает первое число месяца и переходит к
    вводу остатков на день перед ним.
    """
    _name = 'coop.rsbu.start'
    _description = 'Начать учёт в РСБУ'

    organization_id = fields.Many2one(
        'res.partner', string='Организация', required=True, readonly=True)
    start_date = fields.Date(
        string='Учёт в слое с', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1)
                             + relativedelta(months=1),
        help='Первое число месяца. Документы раньше этой даты в слой не '
             'попадают — остатки на день перед ней вводятся следующим шагом.')
    vat_regime = fields.Selection(
        VAT_REGIMES, string='Режим НДС на эту дату', compute='_compute_vat_regime')

    @api.depends('organization_id', 'start_date')
    def _compute_vat_regime(self):
        for wizard in self:
            wizard.vat_regime = wizard.start_date and \
                wizard.organization_id._coop_vat_regime_at(wizard.start_date)

    def action_start(self):
        self.ensure_one()
        org = self.organization_id
        if org not in self.env.user.coop_treasury_partner_ids:
            raise AccessError(_(
                'Начать учёт в РСБУ может тот, у кого у «%s» полномочие '
                '«Бухгалтерия и счета».') % org.name)
        if self.start_date.day != 1:
            raise UserError(_('Учёт в слое начинается с первого числа месяца.'))
        if not self.vat_regime:
            raise UserError(_(
                'У «%s» не указан режим НДС на %s — укажите его на карточке '
                'организации.') % (org.name, fields.Date.to_string(self.start_date)))
        company = org._coop_ensure_company()
        company.sudo().write({'rsbu_enabled': True, 'rsbu_start_date': self.start_date})
        action = self.env['ir.actions.act_window']._for_xml_id(
            'rsbu_connector.action_rsbu_opening_balance_wizard')
        action['context'] = {'default_company_id': company.id}
        return action

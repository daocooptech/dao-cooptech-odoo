from odoo import fields, models

# Режим НДС организации (coop.vat.regime) → режим РСБУ-слоя.
RSBU_VAT_MODE_BY_REGIME = {
    'exempt_145': 'vat_exempt',
    'not_payer': 'vat_exempt',
    'usn_5': 'vat_5',
    'usn_7': 'vat_7',
    'general_22': 'vat_22',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _rsbu_vat_mode_at(self, date):
        """Режим НДС в РСБУ-слое — по истории режимов организации на дату.

        Компания учёта организации берёт режим из её карточки; компания без
        организации (платформа) — из своего поля, как у выпуска.
        """
        self.ensure_one()
        org = self.partner_id
        if org.coop_company_id == self:
            regime = org._coop_vat_regime_at(date or fields.Date.context_today(self))
            if regime:
                return RSBU_VAT_MODE_BY_REGIME[regime]
        return super()._rsbu_vat_mode_at(date)

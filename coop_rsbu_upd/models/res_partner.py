from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # В пуле ИНН и КПП организации — coop_inn / coop_kpp (каталог
    # организаций). Штатный inn у нас — синоним vat из l10n_ru_doc и на
    # боевой пуст у всех; vat — с префиксом страны.
    def _rsbu_inn(self):
        self.ensure_one()
        vat = (self.vat or '').strip()
        if vat.upper().startswith('RU'):
            vat = vat[2:]
        return (self.coop_inn or super()._rsbu_inn() or vat or '').strip()

    def _rsbu_kpp(self):
        self.ensure_one()
        return (self.coop_kpp or super()._rsbu_kpp() or '').strip()

"""Идентификатор участника ЭДО на контрагенте — для имени файла обмена.

Ранее поле называлось `edi` (в устаревшем l10n_ru_upd_xml). Переносим в
РСБУ-слой как `rsbu_edo_participant_id`, чтобы отчётность/УПД не зависели
от deprecated-модуля.
"""
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    rsbu_edo_participant_id = fields.Char(
        string='Идентификатор участника ЭДО',
        help='Уникальный идентификатор контрагента в системе ЭДО, '
             'присвоенный оператором (УИПол — получатель — в имени файла '
             'обмена УПД). При обмене не через оператора — GUID участника.')

    # ИНН и КПП для документов слоя (УПД, акт сверки). Пул переопределяет:
    # у него реквизиты организаций — в каталоге (coop_inn / coop_kpp).
    def _rsbu_inn(self):
        self.ensure_one()
        return (getattr(self, 'inn', '') or '').strip()

    def _rsbu_kpp(self):
        self.ensure_one()
        return (getattr(self, 'kpp', '') or '').strip()

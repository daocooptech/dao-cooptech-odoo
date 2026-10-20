from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rsbu_oktmo = fields.Char(
        related='company_id.rsbu_oktmo', readonly=False, string='ОКТМО')
    rsbu_tax_office_code = fields.Char(
        related='company_id.rsbu_tax_office_code', readonly=False,
        string='Код налогового органа')
    rsbu_okved = fields.Char(
        related='company_id.rsbu_okved', readonly=False, string='ОКВЭД')
    rsbu_kbk_usn = fields.Char(
        related='company_id.rsbu_kbk_usn', readonly=False, string='КБК УСН')
    rsbu_kbk_nds = fields.Char(
        related='company_id.rsbu_kbk_nds', readonly=False, string='КБК НДС')
    rsbu_kbk_ndfl = fields.Char(
        related='company_id.rsbu_kbk_ndfl', readonly=False, string='КБК НДФЛ')
    rsbu_kbk_insurance = fields.Char(
        related='company_id.rsbu_kbk_insurance', readonly=False,
        string='КБК страховых взносов')
    rsbu_kbk_injury = fields.Char(
        related='company_id.rsbu_kbk_injury', readonly=False,
        string='КБК взносов на травматизм')
    rsbu_sfr_reg_number = fields.Char(
        related='company_id.rsbu_sfr_reg_number', readonly=False,
        string='Рег. номер в СФР')
    rsbu_profrisk_class = fields.Char(
        related='company_id.rsbu_profrisk_class', readonly=False,
        string='Класс профриска')
    rsbu_signatory_id = fields.Many2one(
        related='company_id.rsbu_signatory_id', readonly=False,
        string='Подписант отчётности')
    rsbu_signatory_is_representative = fields.Boolean(
        related='company_id.rsbu_signatory_is_representative', readonly=False,
        string='Подписант — представитель')
    rsbu_signatory_title = fields.Char(
        related='company_id.rsbu_signatory_title', readonly=False,
        string='Должность подписанта')
    rsbu_ogrn = fields.Char(
        related='company_id.rsbu_ogrn', readonly=False, string='ОГРН')
    rsbu_edo_operator_code = fields.Char(
        related='company_id.rsbu_edo_operator_code', readonly=False,
        string='Код оператора ЭДО (УИОЭДО)')
    rsbu_edo_participant_id = fields.Char(
        related='company_id.rsbu_edo_participant_id', readonly=False,
        string='Идентификатор участника ЭДО')

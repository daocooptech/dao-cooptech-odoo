"""Перенос реквизитов УПД из l10n_ru_upd_xml в поля РСБУ-слоя.

Повторный запуск ничего не портит: заполняются только пустые поля.
Значения по умолчанию у модулей разные (код оператора ЭДО «2BM» у нас,
«000» у слоя), поэтому код оператора переносится явно.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_move_upd_requisites(env):
    counts = {}
    Company = env['res.company'].sudo()
    Partner = env['res.partner'].sudo()
    for company in Company.search([]):
        vals = {}
        if 'edi' in company._fields and company.edi and not company.rsbu_edo_participant_id:
            vals['rsbu_edo_participant_id'] = company.edi
        if 'edi_operator' in company._fields and company.edi_operator \
                and company.rsbu_edo_operator_code in (False, '', '000'):
            vals['rsbu_edo_operator_code'] = company.edi_operator
        if 'chief_id' in company._fields and company.chief_id and not company.rsbu_signatory_id:
            vals['rsbu_signatory_id'] = company.chief_id.id
        if vals:
            company.write(vals)
            counts[company.name] = len(vals)
    partners = 0
    if 'edi' in Partner._fields:
        for partner in Partner.search([('edi', '!=', False), ('rsbu_edo_participant_id', '=', False)]):
            partner.rsbu_edo_participant_id = partner.edi
            partners += 1
    _logger.info('УПД слоя: реквизиты перенесены у компаний %s, ID ЭДО контрагентов %s',
                 counts, partners)

"""Хук установки: предупреждение о несовместимости с l10n_ru_upd_xml.

РСБУ-слой отчётности определяет собственные поля (okei на uom.uom, а также
через смежные модули edi/inn/kpp/okpo на res.company/res.partner), которые
дублируют поля устаревшего модуля l10n_ru_upd_xml. Совместная установка
может привести к неоднозначному определению полей и некорректной генерации
УПД. Старый модуль помечен deprecated и должен быть удалён.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_check_upd_conflict(env):
    """Предупредить, если установлен устаревший l10n_ru_upd_xml."""
    module = env['ir.module.module'].sudo().search([
        ('name', '=', 'l10n_ru_upd_xml'),
        ('state', '=', 'installed'),
    ], limit=1)
    if module:
        _logger.warning(
            'НЕСОВМЕСТИМОСТЬ: установлен устаревший модуль l10n_ru_upd_xml. '
            'РСБУ-слой формирует УПД из rsbu.invoice (rsbu_fns_reporting) и '
            'определяет собственные поля отчётности (ОКЕИ и др.), которые '
            'конфликтуют со старым модулем. Удалите l10n_ru_upd_xml во '
            'избежание некорректной генерации УПД и дублирования полей.')

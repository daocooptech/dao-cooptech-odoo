# -*- coding: utf-8 -*-
"""Pre-migration для разделения rsbu.invoice на реализацию + СФ.

Снимает снимок передаточных полей (upd_*) отгрузочных СФ ДО того, как новая
схема снимет эти колонки с rsbu_invoice. Снимок переживёт загрузку новой
модели и используется post-скриптом для построения rsbu.realization.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # Снимок строится ТОЛЬКО если колонки upd_* ещё существуют (защита от
    # повторного прогона pre-скрипта после снятия колонок).
    cr.execute("""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.columns
                     WHERE table_name = 'rsbu_invoice'
                       AND column_name = 'upd_shipper_id') THEN
            CREATE TABLE IF NOT EXISTS _mig_upd_snapshot AS
            SELECT id AS invoice_id, source_model, source_res_id,
                   origin_move_id,
                   upd_shipper_id, upd_consignee_id, upd_transferred_by_id,
                   upd_received_by_id, upd_transport, upd_basis,
                   upd_operation_content,
                   partner_id, company_id, date, base_amount, vat_amount,
                   vat_rate, state
            FROM rsbu_invoice
            WHERE invoice_type = 'shipment';
          END IF;
        END $$;
    """)
    _logger.info('rsbu_vat pre-migrate 19.0.2026.10.01 ran')

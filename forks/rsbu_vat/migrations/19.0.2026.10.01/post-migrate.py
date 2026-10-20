# -*- coding: utf-8 -*-
"""Post-migration: построить rsbu.realization из снимка отгрузочных СФ.

Для каждой строки _mig_upd_snapshot (= бывший отгрузочный СФ) создаёт документ
реализации через ORM (чтобы отработал create-хук номера реализации), переносит
передаточные upd_* поля, восстанавливает amount_untaxed/amount_tax из
исходного account.move (фолбэк — base_amount/vat_amount СФ) и связывает
реализацию с СФ двусторонне. Идемпотентно: NO-OP при отсутствии снимка;
реализации создаются только для СФ с realization_id IS NULL.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # NO-OP guard: нет снимка — нечего мигрировать (повторный прогон).
    cr.execute("SELECT to_regclass('_mig_upd_snapshot')")
    if cr.fetchone()[0] is None:
        _logger.info('rsbu_vat post-migrate 19.0.2026.10.01: no snapshot, '
                     'nothing to migrate')
        return

    cr.execute("""
        SELECT invoice_id, source_model, source_res_id, origin_move_id,
               upd_shipper_id, upd_consignee_id, upd_transferred_by_id,
               upd_received_by_id, upd_transport, upd_basis,
               upd_operation_content,
               partner_id, company_id, date, base_amount, vat_amount,
               vat_rate, state
        FROM _mig_upd_snapshot
    """)
    rows = cr.dictfetchall()

    env = api.Environment(cr, SUPERUSER_ID, {})
    Realization = env['rsbu.realization']
    Invoice = env['rsbu.invoice']
    Move = env['account.move']

    created = 0
    for row in rows:
        invoice = Invoice.browse(row['invoice_id'])
        if not invoice.exists() or invoice.realization_id:
            # Нет СФ или уже связан — не плодим дубликаты.
            continue
        real = Realization.create({
            'partner_id': row['partner_id'],
            'company_id': row['company_id'],
            'date': row['date'],
            'source_model': row['source_model'],
            'source_res_id': row['source_res_id'],
            'state': row['state'],
            'upd_shipper_id': row['upd_shipper_id'],
            'upd_consignee_id': row['upd_consignee_id'],
            'upd_transferred_by_id': row['upd_transferred_by_id'],
            'upd_received_by_id': row['upd_received_by_id'],
            'upd_transport': row['upd_transport'],
            'upd_basis': row['upd_basis'],
            'upd_operation_content': row['upd_operation_content'],
        })
        src = Move.browse(row['source_res_id']) if row['source_res_id'] else Move
        real.write({
            'amount_untaxed': src.amount_untaxed if src.exists()
            else row['base_amount'],
            'amount_tax': src.amount_tax if src.exists() else row['vat_amount'],
        })
        # Двусторонняя связь реализация <-> СФ.
        invoice.realization_id = real.id
        real.invoice_id = invoice.id
        created += 1

    cr.execute("DROP TABLE IF EXISTS _mig_upd_snapshot")
    _logger.info('rsbu_vat post-migrate 19.0.2026.10.01 ran: %s realizations '
                 'created', created)

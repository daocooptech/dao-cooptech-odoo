"""res.bank (provisional model, commit 86be3cc) becomes ru.bank.

Odoo 20 has no `res.bank`. The provisional directory model is renamed to
`ru.bank` and `res.bank.corracc` to `ru.bank.corracc`; the account field
`res.partner.bank.bank_id` becomes `ru_bank_id`. The columns `state` and
`country` become `state_id` and `country_id`. Runs before the module data is
loaded, so the ORM finds the renamed tables and fields.
"""


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column))
    return bool(cr.fetchone())


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s)", (table,))
    return bool(cr.fetchone()[0])


def _drop_constraints_and_indexes(cr, table):
    """Drop everything but the primary key: the ORM recreates it under new names."""
    cr.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass AND contype IN ('f', 'u')",
        (table,))
    for (name,) in cr.fetchall():
        cr.execute('ALTER TABLE "%s" DROP CONSTRAINT "%s"' % (table, name))
    cr.execute(
        "SELECT i.relname FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid "
        "WHERE x.indrelid = %s::regclass AND NOT x.indisprimary",
        (table,))
    for (name,) in cr.fetchall():
        cr.execute('DROP INDEX IF EXISTS "%s"' % name)


def migrate(cr, version):
    if not _table_exists(cr, "res_bank"):
        return  # nothing provisional to convert (fresh install)

    # correspondent accounts that l10n_ru_doc kept on the bank itself
    if _column_exists(cr, "res_bank", "corr_acc"):
        cr.execute("""
            INSERT INTO res_bank_corracc (bank_id, corr_acc, create_uid, create_date, write_uid, write_date)
            SELECT b.id, b.corr_acc, 1, now() AT TIME ZONE 'UTC', 1, now() AT TIME ZONE 'UTC'
              FROM res_bank b
             WHERE COALESCE(b.corr_acc, '') != ''
               AND NOT EXISTS (SELECT 1 FROM res_bank_corracc c
                                WHERE c.bank_id = b.id AND c.corr_acc = b.corr_acc)
        """)
        cr.execute("ALTER TABLE res_bank DROP COLUMN corr_acc")
        cr.execute("""
            DELETE FROM ir_model_data WHERE model = 'ir.model.fields' AND res_id IN
                (SELECT id FROM ir_model_fields WHERE model = 'res.bank' AND name = 'corr_acc')
        """)
        cr.execute("DELETE FROM ir_model_fields WHERE model = 'res.bank' AND name = 'corr_acc'")

    # views of the old model: the data files create new ones (children first)
    cr.execute("""
        DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id IN
            (SELECT id FROM ir_ui_view WHERE model = 'res.bank')
    """)
    cr.execute("DELETE FROM ir_ui_view WHERE model = 'res.bank' AND inherit_id IS NOT NULL")
    cr.execute("DELETE FROM ir_ui_view WHERE model = 'res.bank'")

    # tables, sequences, columns
    for old, new in (("res_bank", "ru_bank"), ("res_bank_corracc", "ru_bank_corracc")):
        _drop_constraints_and_indexes(cr, old)
        cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (old, new))
        cr.execute('ALTER SEQUENCE IF EXISTS "%s_id_seq" RENAME TO "%s_id_seq"' % (old, new))
        cr.execute('ALTER TABLE "%s" RENAME CONSTRAINT "%s_pkey" TO "%s_pkey"' % (new, old, new))
    if _column_exists(cr, "ru_bank", "state"):
        cr.execute('ALTER TABLE ru_bank RENAME COLUMN "state" TO state_id')
    if _column_exists(cr, "ru_bank", "country"):
        cr.execute('ALTER TABLE ru_bank RENAME COLUMN country TO country_id')
    if _column_exists(cr, "res_partner_bank", "bank_id"):
        cr.execute("""
            SELECT conname FROM pg_constraint
             WHERE conrelid = 'res_partner_bank'::regclass AND contype = 'f'
               AND conkey = ARRAY[(SELECT attnum FROM pg_attribute
                                    WHERE attrelid = 'res_partner_bank'::regclass AND attname = 'bank_id')]
        """)
        for (name,) in cr.fetchall():
            cr.execute('ALTER TABLE res_partner_bank DROP CONSTRAINT "%s"' % name)
        cr.execute('DROP INDEX IF EXISTS res_partner_bank__bank_id_index')
        cr.execute("ALTER TABLE res_partner_bank RENAME COLUMN bank_id TO ru_bank_id")

    # model and field metadata
    cr.execute("UPDATE ir_model SET model = 'ru.bank' WHERE model = 'res.bank'")
    cr.execute("UPDATE ir_model SET model = 'ru.bank.corracc' WHERE model = 'res.bank.corracc'")
    cr.execute("UPDATE ir_model_fields SET model = 'ru.bank' WHERE model = 'res.bank'")
    cr.execute("UPDATE ir_model_fields SET model = 'ru.bank.corracc' WHERE model = 'res.bank.corracc'")
    cr.execute("UPDATE ir_model_fields SET relation = 'ru.bank' WHERE relation = 'res.bank'")
    cr.execute("UPDATE ir_model_fields SET relation = 'ru.bank.corracc' WHERE relation = 'res.bank.corracc'")
    cr.execute("UPDATE ir_model_fields SET name = 'state_id' WHERE model = 'ru.bank' AND name = 'state'")
    cr.execute("UPDATE ir_model_fields SET name = 'country_id' WHERE model = 'ru.bank' AND name = 'country'")
    cr.execute(
        "UPDATE ir_model_fields SET name = 'ru_bank_id' WHERE model = 'res.partner.bank' AND name = 'bank_id'")

    # external ids: models, fields, data created by the CBR wizard
    cr.execute("""
        UPDATE ir_model_data SET name = regexp_replace(name, '^model_res_bank', 'model_ru_bank')
         WHERE model = 'ir.model' AND name IN ('model_res_bank', 'model_res_bank_corracc')
    """)
    cr.execute("""
        UPDATE ir_model_data SET name = regexp_replace(name, '^field_res_bank_corracc__', 'field_ru_bank_corracc__')
         WHERE model = 'ir.model.fields' AND name LIKE 'field_res_bank_corracc__%'
    """)
    cr.execute("""
        UPDATE ir_model_data SET name = regexp_replace(name, '^field_res_bank__', 'field_ru_bank__')
         WHERE model = 'ir.model.fields' AND name LIKE 'field_res_bank__%'
    """)
    cr.execute("UPDATE ir_model_data SET name = 'field_ru_bank__state_id' WHERE name = 'field_ru_bank__state'")
    cr.execute("UPDATE ir_model_data SET name = 'field_ru_bank__country_id' WHERE name = 'field_ru_bank__country'")
    cr.execute(
        "UPDATE ir_model_data SET name = 'field_res_partner_bank__ru_bank_id' "
        "WHERE name = 'field_res_partner_bank__bank_id'")
    cr.execute("UPDATE ir_model_data SET model = 'ru.bank' WHERE model = 'res.bank'")
    cr.execute("UPDATE ir_model_data SET model = 'ru.bank.corracc' WHERE model = 'res.bank.corracc'")
    cr.execute("""
        UPDATE ir_model_data
           SET name = regexp_replace(name, '^res_bank_', 'ru_bank_'), noupdate = TRUE
         WHERE module = 'l10n_ru_banks' AND model IN ('ru.bank', 'ru.bank.corracc')
           AND name ~ '^res_bank_(corracc_)?[0-9]+$'
    """)
    cr.execute("UPDATE ir_act_window SET res_model = 'ru.bank' WHERE res_model = 'res.bank'")

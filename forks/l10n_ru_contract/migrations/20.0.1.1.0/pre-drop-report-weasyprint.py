"""report_weasyprint is gone: the contract form is printed by the standard engine.

The module directory was removed from the code, so Odoo can no longer uninstall
it by the book. On a database where it was installed, its leftovers are deleted
here: the `use_weasyprint` field of `ir.actions.report` (with its column), the
view, the external ids and the module record itself. Nothing else depended on
it except this module, whose dependency row is dropped as well.
"""


def migrate(cr, version):
    cr.execute("SELECT id FROM ir_module_module WHERE name = 'report_weasyprint'")
    row = cr.fetchone()
    if not row:
        return
    module_id = row[0]

    cr.execute("""
        DELETE FROM ir_ui_view WHERE id IN
            (SELECT res_id FROM ir_model_data
              WHERE module = 'report_weasyprint' AND model = 'ir.ui.view')
    """)
    cr.execute("""
        SELECT f.id, f.model, f.name FROM ir_model_fields f
          JOIN ir_model_data d ON d.model = 'ir.model.fields' AND d.res_id = f.id
         WHERE d.module = 'report_weasyprint' AND f.name = 'use_weasyprint'
    """)
    for field_id, model, name in cr.fetchall():
        table = model.replace('.', '_')
        # ir.actions.report is stored in ir_act_report_xml
        if model == 'ir.actions.report':
            table = 'ir_act_report_xml'
        cr.execute('ALTER TABLE "%s" DROP COLUMN IF EXISTS "%s"' % (table, name))
        cr.execute("DELETE FROM ir_model_fields WHERE id = %s", (field_id,))
    cr.execute("DELETE FROM ir_model_data WHERE module = 'report_weasyprint'")
    cr.execute("DELETE FROM ir_module_module_dependency WHERE name = 'report_weasyprint'")
    cr.execute("DELETE FROM ir_module_module_dependency WHERE module_id = %s", (module_id,))
    cr.execute("UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL WHERE id = %s", (module_id,))

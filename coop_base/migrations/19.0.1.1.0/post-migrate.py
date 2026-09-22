# -*- coding: utf-8 -*-
"""Связать членства с записями справочника оснований участия.

Коды отложены в `pre-migrate`; здесь каждому коду находится своя запись
справочника, и связь проставляется напрямую запросом — по одной записи
на код, а не по одной на членство: членств тысячи, кодов семь.

Обновление `role` из `role_id` делается тем же запросом, чтобы не
запускать пересчёт по всей таблице ради значений, которые мы и так
знаем.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'coop_membership'
           AND column_name = 'coop_role_backup'
    """)
    if not cr.fetchone():
        return

    cr.execute("SELECT id, code FROM coop_membership_role")
    roles = dict((code, role_id) for role_id, code in cr.fetchall())
    if not roles:
        _logger.warning('Справочник оснований участия пуст — связи не '
                        'проставлены')
        return

    linked = 0
    for code, role_id in roles.items():
        cr.execute("""
            UPDATE coop_membership
               SET role_id = %s, role = %s
             WHERE coop_role_backup = %s
               AND role_id IS DISTINCT FROM %s
        """, (role_id, code, code, role_id))
        linked += cr.rowcount

    # Членства с кодом, которого в справочнике нет, оставляем как есть и
    # говорим о них вслух: молча назначить им «пайщика» значило бы выдать
    # права по догадке.
    cr.execute("""
        SELECT DISTINCT coop_role_backup FROM coop_membership
         WHERE role_id IS NULL AND coop_role_backup IS NOT NULL
    """)
    orphans = [row[0] for row in cr.fetchall()]
    if orphans:
        _logger.warning('Коды оснований участия без записи в справочнике: '
                        '%s', ', '.join(orphans))

    cr.execute("ALTER TABLE coop_membership DROP COLUMN coop_role_backup")
    _logger.info('Основания участия связаны со справочником: %s членств',
                 linked)

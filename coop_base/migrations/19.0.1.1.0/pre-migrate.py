# -*- coding: utf-8 -*-
"""Сохранить коды оснований участия до того, как поле станет вычисляемым.

`role` было перечислением, которое писали руками; теперь оно считается
от `role_id` — записи справочника (решение 371). В момент обновления
`role_id` ещё пуст, и движок, пересчитывая вычисляемое поле, затёр бы
`role` пустотой у всех членств разом.

Поэтому коды откладываются в сторону здесь, до пересчёта, и
возвращаются в `post-migrate` уже связями.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        ALTER TABLE coop_membership
          ADD COLUMN IF NOT EXISTS coop_role_backup varchar
    """)
    cr.execute("UPDATE coop_membership SET coop_role_backup = role")
    cr.execute("SELECT count(*) FROM coop_membership WHERE role IS NOT NULL")
    _logger.info('Основания участия отложены: %s членств', cr.fetchone()[0])

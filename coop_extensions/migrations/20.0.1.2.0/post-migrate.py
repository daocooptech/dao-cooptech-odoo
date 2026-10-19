# -*- coding: utf-8 -*-
"""Выданные платформой расширения — из меню у всех (владелец 19.10.2026).

«Очистить у всех»: в меню остаются разделы платформы, пункты по участию
(«Управление проектами») и то, что человек подключил из каталога сам —
у таких пунктов есть ссылка на расширение. Меню организаций, выданные
набором 18.10 (подключения без автора), — тоже.
"""
import logging

from odoo.addons.coop_theme.models.coop_sidebar_item import (
    EXTENSION_ITEMS, REQUIRES, RETIRED_EXTENSIONS)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    given = [name for name, _icon, _xmlid in EXTENSION_ITEMS if name not in REQUIRES]
    given += sorted(RETIRED_EXTENSIONS)
    cr.execute("""
        DELETE FROM coop_sidebar_item
         WHERE section = 'ext' AND extension_id IS NULL
           AND NOT is_required AND name = ANY(%s)
    """, [given])
    items = cr.rowcount
    cr.execute("DELETE FROM coop_extension_connection WHERE user_id IS NULL")
    _logger.info('Выданные расширения убраны: пунктов %s, подключений организаций %s',
                 items, cr.rowcount)

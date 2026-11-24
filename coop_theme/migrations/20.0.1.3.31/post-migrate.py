# -*- coding: utf-8 -*-
"""НМА и ЦФА с левой планки убраны: с 24.11.2026 они подкаталоги «Ресурсов».

Меню участника хранится записями, и обязательные пункты сами не уходят.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        DELETE FROM coop_sidebar_item
         WHERE name IN ('Нематериальные активы', 'Цифровые активы')
    """)
    _logger.info('Пунктов НМА и ЦФА из планки убрано: %s', cr.rowcount)

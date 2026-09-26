# -*- coding: utf-8 -*-
"""«Образование» выше «Аналитики» в уже собранных панелях.

Владелец 26.09.2026: «пункт меню образование подними выше аналитики».
Список по умолчанию правится в коде, но панель у каждого участника своя:
у заведённых «Образование» стоит после «Аналитики». Меняем местами только
эти два пункта и только там, где «Образование» ниже, — остальной порядок,
в том числе расставленный участником, не трогаем.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE coop_sidebar_item AS item
           SET sequence = CASE WHEN item.id = edu.id THEN ana.sequence ELSE edu.sequence END
          FROM coop_sidebar_item AS edu
          JOIN coop_sidebar_item AS ana
            ON ana.user_id = edu.user_id AND ana.name = %s AND ana.section = 'ext'
         WHERE edu.name = %s AND edu.section = 'ext'
           AND edu.sequence > ana.sequence
           AND item.id IN (edu.id, ana.id)
    """, ('Аналитика', 'Образование'))
    _logger.info('Панель: «Образование» поднято выше «Аналитики» — %s пунктов', cr.rowcount)

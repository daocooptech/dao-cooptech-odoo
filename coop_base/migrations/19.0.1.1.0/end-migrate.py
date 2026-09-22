# -*- coding: utf-8 -*-
"""Пайщиков в некоммерческих организациях переписать участниками.

Проверка на копии боевой базы 22 сентября 2026 нашла четырнадцать
членств с основанием «пайщик» в некоммерческих организациях. Ровно этот
случай решение 180 от 2 сентября называло проблемой: роль не зависела от
правовой формы, и пайщик заводился где угодно.

Правило теперь есть, но оно срабатывает при записи, а не задним числом —
уже заведённые записи так и остались бы неправильными, и первая же их
правка упёрлась бы в отказ, причина которого сложилась годом раньше.

Переписываем в «участника»: в НКО паёв нет, и называть её членов
пайщиками значит обещать то, чего не будет.

Шаг `end`, а не `post`: данные о ролях загружаются вместе с модулем,
и до их загрузки записи «участника» ещё не существует.
"""
import logging

_logger = logging.getLogger(__name__)

# Чей пай невозможен: в этих формах паевых отношений нет.
WITHOUT_SHARES = ('nonprofit', 'decentralized', 'commercial')


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT id FROM coop_membership_role WHERE code = 'participant'
    """)
    row = cr.fetchone()
    if not row:
        _logger.warning('Роли «участник» нет — пайщиков не переписываю')
        return
    participant = row[0]

    cr.execute("""
        UPDATE coop_membership m
           SET role_id = %s, role = 'participant'
          FROM coop_legal_form_group g
         WHERE g.id = m.org_group_id
           AND g.code IN %s
           AND m.role = 'member'
    """, (participant, WITHOUT_SHARES))
    if cr.rowcount:
        _logger.info('Пайщики вне кооперативов переписаны участниками: %s',
                     cr.rowcount)

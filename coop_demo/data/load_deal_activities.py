# -*- coding: utf-8 -*-
"""Ответственные и дела по сделкам — действиями самих людей (решение 450).

Карточка сделки как в Битрикс24: у каждой стороны ответственный, в блоке
«Что дальше» — дела. Здесь:

- в части организаций, где «Сделки» держат двое и больше, сделку
  передают коллеге — тот, у кого полномочие, своими правами (в ленте
  остаётся смена ответственного, новому приходит извещение);
- по незакрытым сделкам ответственные ставят себе дела — звонок,
  встреча, письмо, документы; часть уже просрочена, часть выполнена с
  итогом в ленте.

Повторяемо: прогон отмечается в параметрах системы и второй раз не идёт. Жребий —
от номера сделки.
"""
import logging
import random
from datetime import date, timedelta

_logger = logging.getLogger(__name__)

MARK = 'coop_demo.deal_activities'
OPEN = ('lead', 'draft', 'agreed', 'active', 'acceptance', 'disputed')
TODO = {
    'lead': [('mail.mail_activity_data_call', 'Перезвонить, уточнить, что нужно'),
             ('mail.mail_activity_data_email', 'Ответить на обращение')],
    'draft': [('mail.mail_activity_data_meeting', 'Встреча: обсудить условия'),
              ('mail.mail_activity_data_email', 'Отправить проект договора'),
              ('mail.mail_activity_data_call', 'Согласовать цену и сроки')],
    'agreed': [('mail.mail_activity_data_todo', 'Подготовить передачу'),
               ('mail.mail_activity_data_call', 'Договориться о дате передачи')],
    'active': [('mail.mail_activity_data_todo', 'Проверить ход исполнения'),
               ('mail.mail_activity_data_email', 'Напомнить о платеже по графику')],
    'acceptance': [('mail.mail_activity_data_todo', 'Подписать акт'),
                   ('mail.mail_activity_data_meeting', 'Приёмка на месте')],
    'disputed': [('mail.mail_activity_data_meeting', 'Встреча по спору'),
                 ('mail.mail_activity_data_todo', 'Собрать документы для разбора')],
}
RESULTS = ['Созвонились, всё в силе.', 'Отправлено, ждём ответа.',
           'Договорились, переносим на следующую неделю.',
           'Сделано, документы в ленте.']


def load_deal_activities(env):
    Deal = env['coop.deal']
    # Ответственные — у всех, у кого их ещё нет (сделки, заведённые
    # загрузчиками до этой версии).
    Deal.sudo().search([])._coop_fill_responsibles()
    Params = env['ir.config_parameter'].sudo()
    if Params.get_str(MARK):
        _logger.info('Дела по сделкам: уже есть, пропускаю')
        return 0
    deals = Deal.sudo().search([('state', 'in', OPEN)], order='id')
    today = date.today()
    made = done = moved = skipped = 0
    for deal in deals:
        rnd = random.Random(20261008 + deal.id)
        # Передача сделки коллеге внутри организации.
        for side in 'ab':
            party = deal['party_%s_id' % side]
            current = deal['responsible_%s_id' % side]
            staff = Deal._coop_side_staff(party)
            if party.is_company and current and len(staff) > 1 and rnd.random() < 0.12:
                other = (staff - current)[rnd.randrange(len(staff) - 1)]
                try:
                    with env.cr.savepoint():
                        deal.with_user(current).write(
                            {'responsible_%s_id' % side: other.id})
                        moved += 1
                except Exception as error:
                    _logger.debug('Передача %s: %s', deal.number, error)
        if rnd.random() > 0.6:
            continue
        for side in rnd.sample('ab', rnd.choice((1, 1, 2))):
            user = deal['responsible_%s_id' % side]
            if not user:
                continue
            xmlid, summary = rnd.choice(TODO[deal.state])
            try:
                with env.cr.savepoint():
                    activity = deal.with_user(user).activity_schedule(
                        xmlid, user_id=user.id, summary=summary,
                        date_deadline=today + timedelta(days=rnd.randint(-12, 21)))
                    made += 1
                    if rnd.random() < 0.25:
                        activity.with_user(user).action_feedback(
                            feedback=rnd.choice(RESULTS))
                        done += 1
            except Exception as error:
                _logger.debug('Дело по %s: %s', deal.number, error)
                skipped += 1
    Params.set_str(MARK, today.isoformat())
    _logger.info('Дела по сделкам: заведено %s (выполнено %s), передано '
                 'коллегам %s, пропущено %s', made, done, moved, skipped)
    return made

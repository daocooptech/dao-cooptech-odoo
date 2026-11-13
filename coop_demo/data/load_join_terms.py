# -*- coding: utf-8 -*-
"""Условия вступления кооперативов (задача 445).

Нечлен в заявлении читает документы и взносы — у демо-кооперативов они
должны быть, и разными: у кого-то взносы «по уставу», кто-то набор
закрыл, у кого-то устав не выложен (решение 679 п. 4 — заявление
заблокировано). Повторный прогон даёт то же самое: всё от номера записи.
"""

ENTRANCE = (0, 500, 1000, 1500, 2000, 3000, 5000)
SHARE = (0, 1000, 3000, 5000, 10000, 25000, 50000, 100000)
CLOSED_NOTES = (
    'набор закрыт до годового собрания в марте',
    'правление принимает заявления раз в квартал, следующий приём — с 1 января',
    'численность ограничена уставом, ждём выхода членов',
    'идёт реорганизация, приём приостановлен',
)


def load_join_terms(env):
    orgs = env['res.partner'].search([
        ('is_company', '=', True), ('coop_is_cooperative', '=', True)],
        order='id')
    for index, org in enumerate(orgs):
        site = (org.website or 'coop-%d.example' % org.id).rstrip('/')
        values = {
            'coop_fees_rules_url': '%s/fees.pdf' % site,
            'coop_profit_rules_url': (
                '%s/profit.pdf' % site if index % 5 else False),
            'coop_report_url': '%s/report-2025.pdf' % site if index % 4 else False,
            'coop_entrance_fee': ENTRANCE[index % len(ENTRANCE)],
            'coop_min_share_fee': SHARE[(index * 3) % len(SHARE)],
            'coop_join_open': index % 9 != 4,
            'coop_join_closed_note': (
                CLOSED_NOTES[index % len(CLOSED_NOTES)] if index % 9 == 4
                else False),
        }
        if index % 11 == 7:
            # Устав не выложен — заявление заблокировано (решение 679).
            values['coop_charter_url'] = False
        elif not org.coop_charter_url:
            values['coop_charter_url'] = '%s/charter.pdf' % site
        org.write(values)
    return len(orgs)

# -*- coding: utf-8 -*-
"""Извещения о сделках — номер и предмет в кавычках (задача 436).

Раньше в фразу вставлялся `display_name` сделки: «По обращению
СД-2026-001303 — Продавец начаты переговоры». Код теперь пишет
«СД-2026-001303 «Продавец»», а уже выданные извещения правим здесь:
подменяем `display_name` своей сделки на новую подпись. У «согласована:
«предмет»» предмет и так стоит в конце — там остаётся только номер.
"""
import html
import re
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MID = re.compile(
    r'(СД-\d{4}-\d{6}) — ([^.<]+?) (начаты переговоры|отменена второй стороной|'
    r'началось исполнение|открыт спор|закрыт администратором|подтверждён акт|'
    r'исполнена:|раскрыты:|вас оценили)')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Note = env['coop.notification'].sudo().with_context(active_test=False)
    notes = Note.search([('res_model', '=', 'coop.deal'), ('res_id', '!=', False)])
    deals = env['coop.deal'].sudo().with_context(active_test=False).browse(
        set(notes.mapped('res_id'))).exists()
    by_id = {d.id: d for d in deals}
    changed = 0
    for note in notes:
        deal = by_id.get(note.res_id)
        body = note.body or ''
        if not deal:
            # Сделки уже нет — подпись по самой фразе: предмет стоит между
            # номером и глаголом.
            new = MID.sub(lambda m: '%s «%s» %s' % m.groups(), body)
            if new != body:
                cr.execute('UPDATE coop_notification SET body = %s WHERE id = %s', (new, note.id))
                changed += 1
            continue
        if not deal.name:
            continue
        new = body
        # Текст хранится как HTML: ищем и как есть, и в экранированном виде.
        for esc in (str, lambda x: html.escape(x, quote=False)):
            old, label = esc(deal.display_name), esc(deal._coop_label())
            number, name = esc(deal.number), esc(deal.name)
            new = new.replace(old, label)
            new = new.replace('%s согласована: «%s»' % (label, name),
                              '%s согласована: «%s»' % (number, name))
        if new != body:
            # Мимо ORM: sanitize и пересчёт дат здесь не нужны, текст тот же.
            cr.execute('UPDATE coop_notification SET body = %s WHERE id = %s', (new, note.id))
            changed += 1
    _logger.info('Извещения о сделках: подпись поправлена у %s из %s', changed, len(notes))

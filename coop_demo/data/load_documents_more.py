# -*- coding: utf-8 -*-
"""Документы как у облачных дисков — наполнение (разбор 25.09.2026).

- Документы демо-наполнения были текстовыми файлами (.txt): ни первой
  страницы на плитке, ни нормального просмотра. Теперь это PDF — лист А4
  с шапкой, сторонами, предметом и строкой подписей.
- У семидесяти документов есть прежняя редакция — «проект» до правок, со
  своим отпечатком; сверка узнаёт и её.
- Журнал: открыт, скачан, сверен — сторонами, в разные дни.
- Ссылки для внешней стороны: действующие, истёкшие, отозванные, с
  паролем и без.
- Корзина: два десятка черновиков, выброшенных в последние недели.
- Избранное главного участника витрины.

Повторный запуск ничего не удваивает.
"""
import base64
import hashlib
import io
import logging
import random
from datetime import datetime, time, timedelta

_logger = logging.getLogger(__name__)

KIND_TITLES = {'contract': 'ДОГОВОР', 'act': 'АКТ ПРИЁМА-ПЕРЕДАЧИ', 'closing': 'ЗАКРЫВАЮЩИЙ ДОКУМЕНТ',
               'protocol': 'ПРОТОКОЛ', 'other': 'ДОКУМЕНТ'}


def _font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from odoo.tools.misc import file_path
    if 'CoopRoboto' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('CoopRoboto', file_path(
            'web/static/fonts/google/Roboto/Roboto-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('CoopRobotoBold', file_path(
            'web/static/fonts/google/Roboto/Roboto-Bold.ttf')))


def _pdf(doc, text, draft=False):
    """Лист А4: шапка, текст документа, строка подписей."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    _font()
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    width, height = A4
    c.setTitle(doc.name or 'Документ')
    c.setFillColorRGB(0.08, 0.42, 0.39)
    c.setFont('CoopRobotoBold', 10)
    c.drawString(50, height - 40, 'ДАО КООПТЕХ')
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont('CoopRobotoBold', 15)
    c.drawCentredString(width / 2, height - 90, KIND_TITLES.get(doc.kind, 'ДОКУМЕНТ'))
    if draft:
        c.setFont('CoopRobotoBold', 11)
        c.setFillColorRGB(0.7, 0.2, 0.15)
        c.drawCentredString(width / 2, height - 108, 'ПРОЕКТ — редакция для согласования')
        c.setFillColorRGB(0.1, 0.1, 0.1)
    y = height - 140
    c.setFont('CoopRoboto', 11)
    for line in (text or '').splitlines():
        while len(line) > 95:
            c.drawString(60, y, line[:95])
            line, y = line[95:], y - 16
        c.drawString(60, y, line)
        y -= 16
        if y < 120:
            break
    y = min(y - 40, 190)
    c.setFont('CoopRoboto', 10)
    c.drawString(60, y, 'Сторона 1: ____________________')
    c.drawString(320, y, 'Сторона 2: ____________________')
    c.setFont('CoopRoboto', 8)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.drawString(50, 40, 'Составлено на платформе ДАО КООПТЕХ · отпечаток SHA-256 файла сверяется в разделе «Документы»')
    c.showPage()
    c.save()
    return out.getvalue()


def _text_of(doc):
    try:
        raw = base64.b64decode(doc.file or b'')
        return raw.decode('utf-8')
    except Exception:
        return doc.name or ''


def pdf_documents(env):
    """Текстовые документы наполнения — в PDF; редакция 1 — вместе с ними."""
    if 'coop.document.version' not in env:
        return 0
    Document = env['coop.document'].sudo().with_context(active_test=False, coop_no_snapshot=True,
                                                         tracking_disable=True)
    docs = Document.search([('file_name', '=like', '%.txt')])
    done = 0
    for doc in docs:
        text = _text_of(doc)
        if not text:
            continue
        data = base64.b64encode(_pdf(doc, text))
        old_print = doc.fingerprint
        doc.write({'file': data, 'file_name': doc.file_name[:-4] + '.pdf'})
        for version in doc.version_ids.filtered(lambda v: v.fingerprint == old_print):
            version.write({'file': data, 'file_name': doc.file_name, 'fingerprint': doc.fingerprint})
        done += 1
    if done:
        _logger.info('Документы: переведено в PDF %s', done)
    return done


def enrich_documents(env, login='dashkevich'):
    if 'coop.document.share' not in env:
        return 0
    Share = env['coop.document.share'].sudo()
    if Share.search_count([], limit=1):
        _logger.info('Документы: редакции, журнал и ссылки уже наполнены')
        return 0
    rnd = random.Random(20260925 + 7)
    now = datetime.now().replace(microsecond=0)
    Document = env['coop.document'].sudo().with_context(coop_no_snapshot=True, tracking_disable=True)
    Version = env['coop.document.version'].sudo()
    Log = env['coop.document.log'].sudo()
    docs = Document.search([('file', '!=', False)])
    if not docs:
        return 0

    def created(doc):
        return doc.create_date or now - timedelta(days=60)

    # Прежние редакции: «проект» за несколько дней до нынешней.
    for doc in rnd.sample(list(docs), k=min(70, len(docs))):
        versions = doc.version_ids.sorted('number')
        if not versions:
            continue
        for version in versions.sorted('number', reverse=True):
            version.number += 1
        first = versions[0]
        earlier = min(first.date, now) - timedelta(days=rnd.randint(2, 20), hours=rnd.randint(1, 9))
        draft = _pdf(doc, _draft_text(doc), draft=True)
        Version.create({
            'document_id': doc.id, 'number': 1,
            'file': base64.b64encode(draft),
            'file_name': (doc.file_name or 'документ.pdf').replace('.pdf', ' (проект).pdf'),
            'fingerprint': hashlib.sha256(draft).hexdigest(),
            'author_id': doc.party_a_id.id, 'date': earlier, 'note': 'проект для согласования',
        })
        Log.create({'document_id': doc.id, 'partner_id': doc.party_a_id.id, 'action': 'uploaded',
                    'date': earlier, 'note': 'редакция 1 — проект'})
        first.note = 'после замечаний второй стороны'
        Log.search([('document_id', '=', doc.id), ('action', '=', 'uploaded'),
                    ('note', '=', 'редакция 1')]).write({'action': 'version', 'note': 'редакция 2'})

    # Журнал: открыт, скачан, сверен — сторонами, после загрузки.
    actions = [('opened', 50), ('downloaded', 25), ('checked_ok', 18), ('checked_bad', 4)]
    rows = []
    for doc in docs:
        for _n in range(rnd.choice([0, 0, 1, 2, 3, 4, 6])):
            action = rnd.choices([a for a, _w in actions], weights=[w for _a, w in actions])[0]
            who = rnd.choice([doc.party_a_id, doc.party_b_id]) or doc.party_a_id
            start = created(doc)
            when = start + (now - start) * rnd.uniform(0.02, 0.98)
            rows.append({'document_id': doc.id, 'partner_id': who.id, 'action': action,
                         'date': when.replace(microsecond=0)})
    Log.create(rows)

    # Ссылки для внешней стороны.
    today = now.date()
    for doc in rnd.sample(list(docs), k=min(55, len(docs))):
        roll = rnd.random()
        vals = {'document_id': doc.id, 'allow_download': rnd.random() < 0.7,
                'views': rnd.choice([0, 0, 1, 2, 3, 5, 9, 14])}
        if roll < 0.55:
            vals['expires_on'] = today + timedelta(days=rnd.randint(2, 30))
        elif roll < 0.75:
            vals['expires_on'] = today - timedelta(days=rnd.randint(1, 40))
        elif roll < 0.88:
            vals['expires_on'] = today + timedelta(days=rnd.randint(5, 20))
            vals['active'] = False
        if rnd.random() < 0.3:
            vals['password'] = 'кооп%04d' % rnd.randint(0, 9999)
        share = Share.create(vals)
        for _v in range(min(share.views, 3)):
            Log.create({'document_id': doc.id, 'partner_id': env.ref('base.public_partner').id,
                        'action': 'external',
                        'date': (created(doc) + (now - created(doc)) * rnd.uniform(0.5, 0.99)).replace(microsecond=0)})

    # Корзина: черновики, выброшенные в последние недели.
    drafts = Document.search([('state', '=', 'draft')])
    for doc in rnd.sample(list(drafts), k=min(24, len(drafts))):
        day = today - timedelta(days=rnd.randint(1, 28))
        doc.write({'active': False, 'trashed_on': day})
        Log.create({'document_id': doc.id, 'partner_id': doc.party_a_id.id, 'action': 'trashed',
                    'date': datetime.combine(day, time(rnd.randint(9, 19), rnd.randint(0, 59)))})

    # Избранное главного участника: десяток своих документов.
    showcase = env['res.users'].sudo().search([('login', '=', login)], limit=1)
    if showcase:
        mine = showcase.coop_actor_partner_ids.ids
        own = Document.search(['|', ('party_a_id', 'in', mine), ('party_b_id', 'in', mine)])
        Fav = env['coop.favorite'].sudo()
        for doc in rnd.sample(list(own), k=min(10, len(own))):
            if not Fav.search_count([('partner_id', '=', showcase.partner_id.id),
                                     ('res_model', '=', 'coop.document'), ('res_id', '=', doc.id)]):
                Fav.create({'partner_id': showcase.partner_id.id, 'res_model': 'coop.document',
                            'res_id': doc.id})
    _logger.info('Документы: редакции, журнал, ссылки, корзина и избранное наполнены')
    return 1


def _draft_text(doc):
    """Текст проекта — то же, но с пометками, которые потом убрали."""
    lines = [
        '%s № %s от %s (проект)' % (KIND_TITLES.get(doc.kind, 'ДОКУМЕНТ').capitalize(),
                                   doc.number or '—',
                                   doc.signed_on.strftime('%d.%m.%Y') if doc.signed_on else '—'),
        '',
        'Сторона 1: %s' % (doc.party_a_id.name or '—'),
        'Сторона 2: %s' % (doc.party_b_id.name or '—'),
        '',
        'Предмет: %s' % (doc.res_label or doc.name or '—'),
        '',
        '[Сроки и сумма — уточнить после согласования]',
        '',
        'Документ составлен на платформе ДАО КООПТЕХ.',
    ]
    return '\n'.join(lines)

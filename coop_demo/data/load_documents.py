# -*- coding: utf-8 -*-
"""Документы — из сделок и закупок, которые уже прошли.

Решение 382 от 22 сентября 2026. Как и извещения, документы порождаются
из случившегося, а не сочиняются: акт без сделки ведёт в пустоту, и
отпечаток у него не от чего считать.

Файл настоящий — небольшой текст с реквизитами. Он нужен не для
красоты: **без содержимого нет и отпечатка**, а весь раздел затеян ради
отпечатка. Документ без файла показал бы пустое поле там, где должно
стоять главное.
"""
import base64
import logging
import random

from odoo import fields

_logger = logging.getLogger(__name__)

# Сколько документов набираем.
#
# Было 180 — и раздел оказался пустым у всех. Причина арифметическая:
# 180 документов на 197 сторон дают по 1,8 бумаги на человека, а у
# владельца, участника шестнадцати сделок, их нашлось четыре.
#
# Документ виден только своим сторонам, и это правильно: акт между двумя
# кооперативами — не публичное чтение. Но раздел, где у каждого лежит
# одна бумага, не показывает ни папок, ни поиска, ни группировок —
# то есть ровно того, ради чего он сделан.
#
# Поэтому документ заводится **на каждую подходящую сделку**, а не на
# случайные сто восемьдесят. Столько их в жизни и бывает: у закрытой
# сделки есть акт, у идущей — договор.
TARGET = 700

# Часть документов остаётся черновиками, часть отменена: раздел, где всё
# подписано, не показывает ни состояний, ни того, как выглядит спорная
# запись.
DRAFT_SHARE = 0.18
CANCELLED_SHARE = 0.06


def _body(kind_label, number, when, party_a, party_b, subject, amount):
    """Текст документа. Настоящий, чтобы отпечаток было от чего считать."""
    lines = [
        '%s № %s от %s' % (kind_label, number, when),
        '',
        'Сторона 1: %s' % (party_a or '—'),
        'Сторона 2: %s' % (party_b or '—'),
        '',
        'Предмет: %s' % (subject or '—'),
    ]
    if amount:
        lines.append('Сумма: %.2f руб.' % amount)
    lines += [
        '',
        'Стороны подтверждают, что обязательства исполнены полностью и',
        'взаимных претензий не имеют.',
        '',
        'Документ составлен на платформе ДАО КООПТЕХ.',
    ]
    return '\n'.join(lines)


# Папки, которые люди заводят на самом деле. Не «Документы 1»,
# «Документы 2»: полка называется по делу, а не по порядку.
FOLDERS = [
    ('Закупки', ['2026', '2025']),
    ('Поставщики', []),
    ('Налоговая', []),
    ('Спорные', []),
]


def _spread_folders(env, documents, rnd):
    """Разложить часть документов по папкам их владельца.

    **Часть, а не все.** Папка — личный порядок, и в жизни он всегда
    неполон: свежее лежит непонятно где, руки доходят позже. Каталог, в
    котором разложено всё до последней записи, показывает не порядок, а
    то, что его расставила программа.

    Группа «Не разложено» нужна не меньше остальных: по ней человек
    находит то, до чего не дошли руки.
    """
    Folder = env['coop.document.folder'].sudo()
    made = 0
    by_owner = {}
    for document in documents:
        by_owner.setdefault(document.party_a_id, env['coop.document'].sudo())
        by_owner[document.party_a_id] |= document

    for owner, papers in by_owner.items():
        # Папки заводим тому, у кого есть что раскладывать. Порог в две
        # бумаги, а не в три: при трёх без полок оставалось четыре пятых
        # каталога, и группировка по папкам показывала одну огромную
        # кучу «Не разложено» — то есть ровно то, от чего папки и спасают.
        if not owner or len(papers) < 2:
            continue
        shelves = env['coop.document.folder'].sudo()
        for name, children in FOLDERS:
            top = Folder.search([('partner_id', '=', owner.id),
                                 ('name', '=', name),
                                 ('parent_id', '=', False)], limit=1)
            if not top:
                top = Folder.create({'name': name, 'partner_id': owner.id})
            shelves |= top
            for child in children:
                inside = Folder.search([('partner_id', '=', owner.id),
                                        ('name', '=', child),
                                        ('parent_id', '=', top.id)], limit=1)
                if not inside:
                    inside = Folder.create({
                        'name': child, 'partner_id': owner.id,
                        'parent_id': top.id})
                shelves |= inside

        for document in papers:
            if rnd.random() < 0.22:
                continue  # до этого руки не дошли — так и бывает
            fit = shelves
            if document.kind == 'closing':
                closing = shelves.filtered(
                    lambda f: f.parent_id and f.parent_id.name == 'Закупки')
                fit = closing or shelves
            document.folder_id = fit[rnd.randrange(len(fit))]
            made += 1
    _logger.info('Документы: разложено по папкам %s', made)
    return made


def load_documents(env, target=TARGET):
    Document = env['coop.document'].sudo()
    if Document.search_count([]) >= target // 2:
        # Папки появились позже самих документов, и у наполненной базы их
        # нет. Раскладываем на уже заведённых — иначе группировку по
        # папкам увидит только тот, кто начал с чистой базы.
        #
        # Ровно эта ловушка была с ролями закупок: ранний выход
        # пропускал не только создание, но и всё, что добавили потом.
        _spread_folders(env, Document.search([]), random.Random(20260923))
        _logger.info('Документы: уже наполнены, разложил по папкам')
        return 0

    rnd = random.Random(20260923)
    lines = []

    # Все сделки, а не первые сто восемьдесят: документ принадлежит
    # сделке, и брать их «сколько поместится» значит оставить половину
    # участников без единой бумаги.
    deals = env['coop.deal'].sudo().search(
        [('state', 'not in', ('draft', 'cancelled'))], order='id desc')
    for deal in deals:
        if not deal.party_a_id or not deal.party_b_id:
            continue
        # Акт — у закрытых сделок, договор — у идущих. Акт по сделке,
        # которая ещё в переговорах, — бессмыслица, и на витрине она
        # видна сразу.
        closed = deal.state in ('done', 'closed', 'paid')
        kind = 'act' if closed else 'contract'
        label = 'Акт приёма-передачи' if closed else 'Договор'
        when = deal.signed_on or fields.Date.context_today(Document)
        number = deal.number or str(deal.id)
        # Предмет, а не номер: номер стоит своей колонкой.
        # `subject` у сделки — перечисление, и наружу оно отдаёт код.
        # Человеческое название лежит в `name`, а полное имя записи
        # начинается с номера: «СД-2026-000481 — Складское место…».
        about = (deal.name or deal.display_name or '').strip()
        if about.startswith(number):
            about = about[len(number):].lstrip(' —-:')
        lines.append({
            'name': '%s — %s' % (label, about) if about else label,
            'kind': kind,
            'party_a_id': deal.party_a_id.id,
            'party_b_id': deal.party_b_id.id,
            'signed_on': when,
            'number': number,
            'res_model': 'coop.deal',
            'res_id': deal.id,
            'res_label': deal.display_name,
            'text': _body(label, number, when, deal.party_a_id.display_name,
                          deal.party_b_id.display_name,
                          deal.display_name, deal.amount or 0.0),
        })

    buys = env['coop.groupbuy'].sudo().search(
        [('state', 'in', ('handout', 'done'))], order='id desc')
    for buy in buys:
        if not buy.organizer_id:
            continue
        when = buy.received_on or buy.stop_date
        number = 'ЗК-%s' % buy.id
        lines.append({
            'name': 'Закрывающий документ — %s' % buy.name,
            'kind': 'closing',
            'party_a_id': buy.organizer_id.id,
            'party_b_id': (buy.supplier_id.id if buy.supplier_id else False),
            'signed_on': when,
            'number': number,
            'res_model': 'coop.groupbuy',
            'res_id': buy.id,
            'res_label': buy.display_name,
            'text': _body('Закрывающий документ', number, when,
                          buy.organizer_id.display_name,
                          buy.supplier_id.display_name if buy.supplier_id
                          else buy.supplier_name,
                          buy.name, buy.total_amount or 0.0),
        })

    if not lines:
        _logger.warning('Документы: сделок и закупок не нашлось')
        return 0

    rnd.shuffle(lines)
    lines = lines[:target]

    values = []
    for line in lines:
        text = line.pop('text')
        chance = rnd.random()
        if chance < CANCELLED_SHARE:
            line['state'] = 'cancelled'
        elif chance < CANCELLED_SHARE + DRAFT_SHARE:
            line['state'] = 'draft'
        else:
            line['state'] = 'signed'
        line['file'] = base64.b64encode(text.encode('utf-8'))
        line['file_name'] = '%s.txt' % line['number'].replace('/', '-')
        values.append(line)

    created = Document.create(values)
    _spread_folders(env, created, rnd)
    signed = sum(1 for v in values if v['state'] == 'signed')
    _logger.info('Документы: создано %s, подписанных %s', len(created), signed)
    return len(created)

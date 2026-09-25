# -*- coding: utf-8 -*-
"""Редакции и журнал для документов, заведённых до них.

С этой версии у документа есть редакции (каждая со своим отпечатком) и
журнал действий. У уже заведённых документов текущий файл становится
редакцией 1, в журнал ложится «Загружен» датой создания; у подписанных
редакция закрепляется и пишется «Подписан» датой подписания.
"""
from datetime import datetime, time

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Document = env['coop.document'].with_context(active_test=False)
    Version = env['coop.document.version']
    Log = env['coop.document.log']
    done = 0
    for doc in Document.search([]):
        if Version.search_count([('document_id', '=', doc.id)], limit=1):
            continue
        try:
            file = doc.file
        except Exception:
            file = False
        if not file:
            continue
        created = doc.create_date or datetime.now()
        Version.create({
            'document_id': doc.id, 'number': 1, 'file': file,
            'file_name': doc.file_name, 'fingerprint': doc.fingerprint,
            'author_id': doc.party_a_id.id, 'date': created,
            'pinned': doc.state == 'signed',
        })
        Log.create({'document_id': doc.id, 'partner_id': doc.party_a_id.id,
                    'action': 'uploaded', 'date': created, 'note': 'редакция 1'})
        if doc.state == 'signed':
            signed = datetime.combine(doc.signed_on, time(12)) if doc.signed_on else created
            Log.create({'document_id': doc.id, 'partner_id': doc.party_a_id.id,
                        'action': 'signed', 'date': max(signed, created),
                        'note': 'редакция 1 закреплена'})
        done += 1
    print('coop_documents: редакция 1 и журнал — у %s документов' % done)

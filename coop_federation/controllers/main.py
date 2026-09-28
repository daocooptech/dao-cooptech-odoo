# -*- coding: utf-8 -*-
"""Две обязательные точки протокола: DID-документ и журнал.

`save_session=False` обязателен: без него каждый опрос соседа заводил бы
сессию на диске и вешал куку — а ответ с кукой nginx не кэширует (записано
в «Граблях Odoo»). Ответы собираются из подписанных данных, поэтому
`sudo()` здесь не расширяет доступ: отдаётся только то, что узел и так
публикует всем, а тела адресных событий — только подтвердившему себя адресату.
"""
import json

from odoo import http
from odoo.http import request

from ..lib.fedproto import log as fed_log, reader as fed_reader
from ..models.fed_identity import utc_now

MAX_LIMIT = 1000


def _json(payload, status=200, cache='no-store'):
    return request.make_response(
        json.dumps(payload, ensure_ascii=False),
        headers=[('Content-Type', 'application/json; charset=utf-8'),
                 ('Cache-Control', cache)],
        status=status)


class CoopFederation(http.Controller):

    @http.route('/.well-known/did.json', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False, readonly=True)
    def did_json(self, **kw):
        identity = request.env['coop.fed.identity'].sudo().search([], limit=1)
        if not identity:
            return _json({'error': 'узел не заведён'}, status=404)
        return _json(identity.did_document(), cache='public, max-age=300')

    @http.route('/federation/log', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False, readonly=True)
    def log(self, **kw):
        identity = request.env['coop.fed.identity'].sudo().search([], limit=1)
        if not identity:
            return _json({'error': 'узел не заведён'}, status=404)
        query = request.httprequest.args.to_dict()
        try:
            since = max(0, int(query.get('since', 0)))
            limit = max(1, min(int(query.get('limit', 100)), MAX_LIMIT))
        except ValueError:
            return _json({'error': 'since и limit — целые числа'}, status=400)

        reader = None
        claimed = query.get('for')
        if claimed:
            # Ключи читателя — из его DID-документа, скачанного заранее
            # (соседи, шаг 2). Незнакомый читатель — просто посторонний.
            ring = fed_log.KeyRing()
            keys = request.env['coop.fed.key'].sudo().search([('owner_did', '=', claimed)])
            for key in keys:
                ring.add(key.kid, fed_log.unb64(key.public_key),
                         since=key.not_before or '0000-01-01T00:00:00Z',
                         revoked=key.revoked_at or None, compromised=key.compromised_at or None)
            reader = fed_reader.verify(request.httprequest.headers, 'GET',
                                       request.httprequest.path, query, ring, utc_now())

        events = request.env['coop.fed.event'].sudo().journal(
            identity, since=since, limit=limit, reader=reader)
        payload = {'events': events, 'head': identity.head()}
        if len(events) == limit:
            payload['next'] = events[-1]['seq'] + 1
        return _json(payload)

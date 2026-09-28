# -*- coding: utf-8 -*-
"""Соседи: чей журнал мы читаем и как.

Приём устроен так, чтобы ни один сосед не мог испортить нам ни журнал, ни
состояние:

1. ключи соседа — только из его DID-документа; незнакомый ключ — документ
   перечитывается один раз, не помогло — стоп;
2. каждое событие проверяется эталоном (`log.check`): подпись, хэш конверта,
   время. Не прошло — чтение останавливается и курсор не двигается: дальше
   ничего не принимаем, пока человек не разберётся;
3. автор события обязан быть этим соседом, номера идут подряд и `prev`
   указывает на предыдущее событие — иначе стоп;
4. подпись верна, но предмет чужой (правило владения) — событие сохраняется
   отвергнутым: цепочка соседа цела, а применять его нельзя;
5. незнакомый тип сохраняется как есть и не применяется — сеть переживает
   разные версии участников;
6. подписанная голова журнала сравнивается с тем, что мы уже видели:
   другое событие под тем же номером или откат номера назад — раздвоение,
   улика; фиксируется с обеими подписями.

Чтение идемпотентно: повтор страницы ничего не дублирует — событие с тем же
идентификатором уже есть.
"""
import datetime
import json
import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..lib.fedproto import did as fed_did, log as fed_log, ownership, reader as fed_reader
from .fed_identity import utc_now

_logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
PAGE = 200
MAX_PAGES = 10          # за один проход: не занимать единственный поток заданий


class CoopFedPeer(models.Model):
    _name = 'coop.fed.peer'
    _description = 'Сосед по сети'
    _order = 'name, did'

    name = fields.Char('Название')
    did = fields.Char('Идентификатор (did:web)', required=True, index=True)
    base_url = fields.Char(
        'Адрес вместо стандартного',
        help='Для узла без https или на стенде: http://217.15.207.46. Пусто — адрес по did:web.')
    state = fields.Selection([('active', 'Читаем'), ('paused', 'Пауза'), ('blocked', 'Заблокирован')],
                             string='Состояние', default='active', required=True)
    did_doc = fields.Text('DID-документ', readonly=True)
    did_fetched_at = fields.Char('Документ скачан', readonly=True)
    cursor_seq = fields.Integer('Следующий номер', default=0, readonly=True)
    last_event = fields.Char('Последнее принятое событие', readonly=True)
    last_head = fields.Text('Последняя голова', readonly=True)
    last_pull_at = fields.Char('Последнее чтение', readonly=True)
    last_error = fields.Char('Последняя ошибка', readonly=True)
    fail_count = fields.Integer('Неудач подряд', readonly=True)
    next_try_at = fields.Datetime('Следующая попытка', readonly=True)
    country_id = fields.Many2one('res.country', string='Страна (из объявления узла)', readonly=True)
    event_count = fields.Integer('Событий принято', compute='_compute_event_count')
    divergence_ids = fields.One2many('coop.fed.divergence', 'peer_id', string='Расхождения')

    _did_uniq = models.Constraint('unique(did)', 'Такой сосед уже есть.')

    @api.constrains('did')
    def _check_did(self):
        for peer in self:
            if not fed_log.DID_RE.match(peer.did or ''):
                raise UserError('Это не did:web: %s' % peer.did)
            own = self.env['coop.fed.identity'].sudo().search([], limit=1)
            if own and own.did == peer.did:
                raise UserError('Свой узел соседом не бывает.')

    def _compute_event_count(self):
        Event = self.env['coop.fed.event'].sudo()
        for peer in self:
            peer.event_count = Event.search_count([('node', '=', peer.did)])

    # -- сеть -------------------------------------------------------------

    def _url(self, path):
        self.ensure_one()
        if self.base_url:
            return self.base_url.rstrip('/') + path
        if path == '/.well-known/did.json':
            return fed_did.url(self.did)
        return fed_did.url(self.did).rsplit('/.well-known/did.json', 1)[0] + path

    def _http_get(self, url, params=None, headers=None):
        """Одна точка выхода в сеть — её подменяют тесты."""
        response = requests.get(url, params=params, headers=headers or {},
                                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False)
        response.raise_for_status()
        return response.json()

    # -- ключи ------------------------------------------------------------

    def action_fetch_did(self):
        for peer in self:
            peer._fetch_did()
        return True

    def _fetch_did(self):
        """Скачать документ соседа и разложить ключи. Документ, выданный за
        другой узел, отвергается."""
        self.ensure_one()
        doc = self._http_get(self._url('/.well-known/did.json'))
        ring = fed_did.keyring(doc, self.did)
        Key = self.env['coop.fed.key'].sudo()
        for kid, entry in ring.keys.items():
            values = {
                'owner_did': self.did,
                'public_key': fed_log.b64(entry['key']),
                'not_before': entry['since'],
                'revoked_at': entry['revoked'] or False,
                'compromised_at': entry['compromised'] or False,
            }
            existing = Key.search([('kid', '=', kid)], limit=1)
            if existing:
                if existing.public_key != values['public_key']:
                    # Тот же kid с другим ключом — подмена или ошибка соседа.
                    raise UserError('Сосед %s сменил ключ %s без нового идентификатора ключа.'
                                    % (self.did, kid))
                existing.write({k: v for k, v in values.items() if k != 'public_key'})
            else:
                Key.create(dict(values, kid=kid, purpose='working'))
        self.write({'did_doc': json.dumps(doc, ensure_ascii=False), 'did_fetched_at': utc_now()})
        return ring

    def _keyring(self):
        self.ensure_one()
        ring = fed_log.KeyRing()
        for key in self.env['coop.fed.key'].sudo().search([('owner_did', '=', self.did)]):
            ring.add(key.kid, fed_log.unb64(key.public_key),
                     since=key.not_before or '0000-01-01T00:00:00Z',
                     revoked=key.revoked_at or None, compromised=key.compromised_at or None)
        return ring

    # -- чтение -----------------------------------------------------------

    def action_pull(self):
        for peer in self:
            peer._pull()
        return True

    def _request_headers(self, query):
        """Подписать запрос своим ключом — тогда сосед отдаст тела событий,
        адресованных нам. Нечем подписать — читаем как посторонний."""
        identity = self.env['coop.fed.identity'].sudo().search([], limit=1)
        if not identity:
            return {}
        try:
            key, secret = identity._secret()
        except UserError:
            return {}
        return fed_reader.sign(identity.did, key.kid, secret, 'GET', '/federation/log',
                               query, utc_now())

    def _pull(self):
        """Прочитать журнал соседа с курсора. Возвращает число принятых событий."""
        self.ensure_one()
        if self.state != 'active':
            return 0
        identity = self.env['coop.fed.identity'].sudo().search([], limit=1)
        accepted = 0
        try:
            if not self.did_doc:
                self._fetch_did()
            ring = self._keyring()
            refetched = False
            for _page in range(MAX_PAGES):
                query = {'since': str(self.cursor_seq), 'limit': str(PAGE)}
                if identity:
                    query['for'] = identity.did
                payload = self._http_get(self._url('/federation/log'), params=query,
                                         headers=self._request_headers(query))
                events = payload.get('events') or []
                for event in events:
                    try:
                        status = fed_log.check(event, ring, utc_now())
                    except fed_log.Invalid as error:
                        if refetched or 'неизвестен' not in str(error):
                            raise
                        ring = self._fetch_did()        # новый ключ соседа — один раз
                        refetched = True
                        status = fed_log.check(event, ring, utc_now())
                    self._accept(event, status)
                    accepted += 1
                if payload.get('head'):
                    self._check_head(payload['head'], ring)
                if 'next' not in payload or not events:
                    break
            self.write({'last_pull_at': utc_now(), 'last_error': False,
                        'fail_count': 0, 'next_try_at': False})
        except (requests.RequestException, ValueError, fed_log.Invalid, UserError) as error:
            fails = self.fail_count + 1
            delay = min(2 ** fails, 60)
            self.write({
                'last_error': '%s: %s' % (type(error).__name__, error),
                'fail_count': fails,
                'next_try_at': fields.Datetime.now() + datetime.timedelta(minutes=delay),
            })
            _logger.warning('Федерация: чтение %s остановлено — %s', self.did, error)
        return accepted

    def _accept(self, event, status):
        """Принять одно проверенное событие. Непрерывность — строго."""
        Event = self.env['coop.fed.event'].sudo()
        if event['node'] != self.did:
            raise fed_log.Invalid('в журнале %s событие узла %s' % (self.did, event['node']))
        if Event.search_count([('event_id', '=', event['id'])]):
            if event['seq'] >= self.cursor_seq:
                self.write({'cursor_seq': event['seq'] + 1, 'last_event': event['id']})
            return
        if event['seq'] != self.cursor_seq:
            raise fed_log.Invalid('ждали номер %d, пришёл %d — журнал неполон'
                                  % (self.cursor_seq, event['seq']))
        if event['prev'] != (self.last_event or None):
            raise fed_log.Invalid('разрыв цепочки на номере %d' % event['seq'])

        verdict = ownership.owns(event)
        reason = False
        if verdict is False:
            state, reason = 'rejected', 'событие о чужом предмете: %s' % event['subject']
        elif verdict == ownership.UNKNOWN:
            state = 'unknown_type'
        elif status == fed_log.SUSPECT:
            state = 'suspect'
        else:
            state = 'ok'

        body = event.get('body')
        Event.create({
            'origin': 'peer',
            'node': event['node'],
            'seq': event['seq'],
            'prev': event['prev'],
            'event_id': event['id'],
            'kid': event['kid'],
            'ts': event['ts'],
            'type': event['type'],
            'subject': event['subject'],
            'to_json': json.dumps(event['to']) if 'to' in event else False,
            'body_json': json.dumps(body, ensure_ascii=False, sort_keys=True) if body is not None else False,
            'body_hash': event['body_hash'],
            'sig': event['sig'],
            'raw': json.dumps(event, ensure_ascii=False),
            'status': state,
            'reason': reason,
        })
        if event['type'] == 'node.announced' and state == 'ok' and body:
            country = (body.get('jurisdiction') or {}).get('country')
            values = {'name': body.get('name') or self.name}
            if country:
                values['country_id'] = self.env['res.country'].search(
                    [('code', '=', country.upper())], limit=1).id
            self.write(values)
        self.write({'cursor_seq': event['seq'] + 1, 'last_event': event['id']})

    def _check_head(self, head, ring):
        """Сверить подписанную голову с принятым: откат или подмена — раздвоение."""
        fed_log.check_head(head, ring)
        if head.get('node') != self.did:
            raise fed_log.Invalid('голова чужого узла')
        Event = self.env['coop.fed.event'].sudo()
        ours = Event.search([('node', '=', self.did), ('seq', '=', head['seq'])], limit=1)
        kind = False
        if head['seq'] < self.cursor_seq - 1:
            kind = 'rollback'
        if ours and ours.event_id != head.get('id'):
            kind = 'fork'
        if kind:
            self.env['coop.fed.divergence'].sudo().create({
                'peer_id': self.id, 'kind': kind, 'seq': head['seq'],
                'ours': ours.raw if ours else False,
                'theirs': json.dumps(head, ensure_ascii=False),
            })
            self.write({'state': 'paused'})
            raise fed_log.Invalid('раздвоение журнала %s на номере %d' % (self.did, head['seq']))
        self.last_head = json.dumps(head, ensure_ascii=False)

    @api.model
    def _cron_pull(self):
        now = fields.Datetime.now()
        peers = self.sudo().search([('state', '=', 'active'), '|',
                                    ('next_try_at', '=', False), ('next_try_at', '<=', now)])
        for peer in peers:
            peer._pull()
            self.env.cr.commit()       # сосед за соседом: сбой одного не откатывает другие


class CoopFedDivergence(models.Model):
    """Доказанное расхождение: сосед показал два разных журнала. Хранится с
    обеими подписями — это улика, а не запись в журнале ошибок."""
    _name = 'coop.fed.divergence'
    _description = 'Расхождение журнала соседа'
    _order = 'create_date desc'

    peer_id = fields.Many2one('coop.fed.peer', string='Сосед', required=True, ondelete='cascade')
    kind = fields.Selection([('fork', 'Другое событие под тем же номером'),
                             ('rollback', 'Журнал откатился назад')], string='Что', required=True)
    seq = fields.Integer('Номер')
    ours = fields.Text('Что мы приняли раньше')
    theirs = fields.Text('Что сосед показывает теперь')

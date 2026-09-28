# -*- coding: utf-8 -*-
"""Чтение журнала соседа. Сосед — эталонный журнал в памяти, сеть подменена:
так проверяется всё, что может прийти по сети, включая подделки."""
import json
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.coop_federation.lib.fedproto import did as fed_did, log as fed_log, reader as fed_reader
from odoo.addons.coop_federation.models.fed_identity import utc_now

PEER = 'did:web:fed-b.koopeh.test'
PEER_SECRET = bytes(range(32, 64))
OTHER_SECRET = bytes(range(64, 96))


class FakePeer(object):
    """Узел-сосед: журнал, документ, выдача ровно как у настоящего."""

    def __init__(self, did=PEER, secret=PEER_SECRET):
        self.log = fed_log.Log(did, did + '#key-1', secret)
        self.keys = [{'kid': self.log.kid, 'public_key': self.log.public_key}]
        self.readers = fed_log.KeyRing()
        self.tamper = None
        self.head_override = None

    def publish(self, type_, subject, body, to=None):
        return self.log.append(utc_now(), type_, subject, body, to=to)

    def document(self):
        return fed_did.document(self.log.node, self.keys)

    def get(self, url, params=None, headers=None):
        if url.endswith('/.well-known/did.json'):
            return self.document()
        events = fed_reader.serve(self.log, headers or {}, '/federation/log', params or {},
                                  self.readers, utc_now())
        events = [dict(e) for e in events]
        if self.tamper:
            self.tamper(events)
        head = self.head_override or self.log.head(utc_now())
        payload = {'events': events, 'head': head}
        if len(events) == int((params or {}).get('limit', 100)):
            payload['next'] = events[-1]['seq'] + 1
        return payload


@tagged('post_install', '-at_install')
class TestPeers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.identity = cls.env['coop.fed.identity']._ensure()
        cls.Event = cls.env['coop.fed.event']

    def setUp(self):
        super().setUp()
        self.fake = FakePeer()
        self.fake.publish('node.announced', PEER, {
            'name': 'Артель «Северный лес»', 'jurisdiction': {'country': 'KZ'}})
        self.peer = self.env['coop.fed.peer'].create({'did': PEER, 'base_url': 'http://fed-b.test'})
        fake = self.fake
        self.patcher = patch.object(type(self.env['coop.fed.peer']), '_http_get',
                                    lambda self_, url, params=None, headers=None: fake.get(url, params, headers))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def events(self):
        return self.Event.search([('node', '=', PEER)], order='seq')

    def test_pull_accepts_and_learns_the_neighbour(self):
        self.fake.publish('catalog.offer.published', PEER + '/offer/1', {'title': 'Доска обрезная'})
        self.assertEqual(self.peer._pull(), 2)
        self.assertEqual(self.peer.cursor_seq, 2)
        self.assertEqual(self.events().mapped('status'), ['ok', 'ok'])
        self.assertEqual(self.peer.name, 'Артель «Северный лес»')
        self.assertEqual(self.peer.country_id.code, 'KZ')
        self.assertFalse(self.peer.last_error)
        # Принятое сходится у эталона так же, как у соседа.
        chain = [json.loads(e.raw) for e in self.events()]
        self.assertEqual(fed_log.check_chain(chain, self.peer._keyring(), utc_now()), fed_log.OK)

    def test_pull_is_idempotent(self):
        self.peer._pull()
        self.assertEqual(self.peer._pull(), 0)
        self.fake.publish('catalog.offer.published', PEER + '/offer/2', {})
        self.assertEqual(self.peer._pull(), 1)
        self.assertEqual(len(self.events()), 2)

    def test_forged_event_stops_reading(self):
        self.peer._pull()
        self.fake.publish('catalog.offer.published', PEER + '/offer/3', {'price': '1.00'})

        def forge(events):
            events[-1]['body'] = {'price': '1000000.00'}
        self.fake.tamper = forge
        self.assertEqual(self.peer._pull(), 0)
        self.assertEqual(self.peer.cursor_seq, 1)
        self.assertIn('Invalid', self.peer.last_error)
        self.assertTrue(self.peer.next_try_at)

    def test_signed_by_someone_else_rejected(self):
        self.fake.keys = [{'kid': PEER + '#key-1', 'public_key': fed_log.Log(
            PEER, PEER + '#key-1', OTHER_SECRET).public_key}]
        self.assertEqual(self.peer._pull(), 0)
        self.assertFalse(self.events())

    def test_gap_in_numbers_stops_reading(self):
        self.peer._pull()
        self.fake.publish('catalog.offer.published', PEER + '/offer/4', {})
        self.fake.publish('catalog.offer.published', PEER + '/offer/5', {})

        def drop_first(events):
            del events[0]
        self.fake.tamper = drop_first
        self.assertEqual(self.peer._pull(), 0)
        self.assertEqual(self.peer.cursor_seq, 1)

    def test_foreign_subject_kept_but_rejected(self):
        own_offer = self.identity.did + '/offer/7'
        self.fake.publish('catalog.offer.withdrawn', own_offer, {'reason': 'снято соседом'})
        self.peer._pull()
        event = self.events()[-1]
        self.assertEqual(event.status, 'rejected')
        self.assertEqual(self.peer.cursor_seq, 2)        # цепочка соседа цела

    def test_unknown_type_kept_as_is(self):
        self.fake.publish('weather.reported', PEER + '/weather/1', {'t': '12'})
        self.peer._pull()
        self.assertEqual(self.events()[-1].status, 'unknown_type')

    def test_addressed_body_reaches_us_only_when_we_sign(self):
        self.fake.publish('deal.proposed', PEER + '/deal/1',
                          {'total': {'amount': '10.00', 'currency': 'RUB'}}, to=[self.identity.did])
        # Сосед знает наш ключ — как если бы скачал наш DID-документ.
        key, _secret = self.identity._secret()
        self.fake.readers.add(key.kid, fed_log.unb64(key.public_key))
        self.peer._pull()
        self.assertIn('10.00', self.events()[-1].body_json)

    def test_addressed_body_hidden_without_our_key(self):
        self.fake.publish('deal.proposed', PEER + '/deal/2', {'secret': 'x'}, to=[self.identity.did])
        self.peer._pull()
        event = self.events()[-1]
        self.assertFalse(event.body_json)
        self.assertEqual(event.status, 'ok')              # конверт проверен и без тела

    def test_fork_is_recorded_with_evidence(self):
        self.peer._pull()
        twin = FakePeer()           # тот же ключ, другая история под тем же номером
        twin.publish('node.announced', PEER, {'name': 'Другая история'})
        self.fake.head_override = twin.log.head(utc_now())
        self.assertEqual(self.peer._pull(), 0)
        self.assertEqual(self.peer.state, 'paused')
        self.assertEqual(self.peer.divergence_ids.kind, 'fork')
        self.assertTrue(self.peer.divergence_ids.ours and self.peer.divergence_ids.theirs)

    def test_new_key_fetched_once(self):
        self.peer._pull()
        rotated = fed_log.Log(PEER, PEER + '#key-2', OTHER_SECRET)
        self.fake.keys.append({'kid': rotated.kid, 'public_key': rotated.public_key})
        self.fake.log.kid, self.fake.log.secret = rotated.kid, OTHER_SECRET
        self.fake.publish('catalog.offer.published', PEER + '/offer/8', {})
        self.assertEqual(self.peer._pull(), 1)
        self.assertTrue(self.env['coop.fed.key'].search([('kid', '=', PEER + '#key-2')]))

    def test_own_node_is_not_a_neighbour(self):
        with self.assertRaises(Exception):
            self.env['coop.fed.peer'].create({'did': self.identity.did})

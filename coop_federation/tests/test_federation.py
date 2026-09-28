# -*- coding: utf-8 -*-
"""Узел сети на движке. Журнал проверяется ЭТАЛОНОМ протокола, а не самим
модулем: иначе движок подтверждал бы сам себя."""
import hashlib
import json
import os

import psycopg2

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.coop_federation.lib import crypto
from odoo.addons.coop_federation.lib.fedproto import did as fed_did, log as fed_log, reader as fed_reader
from odoo.addons.coop_federation.models.fed_identity import did_for_url, utc_now

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib', 'fedproto')
PEER = 'did:web:fed-b.koopeh.test'
PEER_SECRET = bytes(range(32, 64))


def _file_digest(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read().replace(b'\r\n', b'\n')).hexdigest()


@tagged('post_install', '-at_install')
class TestFederationNode(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.identity = cls.env['coop.fed.identity']._ensure()
        cls.Event = cls.env['coop.fed.event']

    def _chain(self):
        events = self.Event.search([('node', '=', self.identity.did), ('status', '=', 'ok')],
                                   order='seq')
        return [e.as_signed() for e in events]

    def test_vendored_protocol_is_untouched(self):
        """Копия эталона не правится на месте: правка — в эталоне, с тестом."""
        with open(os.path.join(LIB, 'SOURCE.txt'), encoding='utf-8') as handle:
            lines = [l.split() for l in handle if l.strip() and not l.startswith('#')]
        self.assertGreaterEqual(len(lines), 8)
        for digest, name in lines:
            self.assertEqual(_file_digest(os.path.join(LIB, name.lstrip('*'))), digest, name)

    def test_crypto_matches_rfc8032(self):
        secret = bytes.fromhex('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb')
        self.assertEqual(crypto.public_key(secret).hex(),
                         '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c')
        self.assertEqual(crypto.sign(secret, b'\x72').hex(),
                         '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da'
                         '085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')
        self.assertTrue(crypto.verify(crypto.public_key(secret), b'\x72', crypto.sign(secret, b'\x72')))
        self.assertFalse(crypto.verify(crypto.public_key(secret), b'\x73', crypto.sign(secret, b'\x72')))

    def test_did_for_url(self):
        self.assertEqual(did_for_url('http://217.15.207.46'), 'did:web:217.15.207.46')
        self.assertEqual(did_for_url('http://localhost:8069/'), 'did:web:localhost%3A8069')
        self.assertEqual(did_for_url('217.15.207.46'), 'did:web:217.15.207.46')
        self.assertEqual(did_for_url('localhost:8070'), 'did:web:localhost%3A8070')
        self.assertTrue(fed_log.DID_RE.match(did_for_url('http://localhost:8069')))

    def test_identity_and_key_file(self):
        self.assertTrue(self.identity.did.startswith('did:web:'))
        key, secret = self.identity._secret()
        self.assertTrue(os.path.isfile(key.secret_path))
        self.assertEqual(fed_log.b64(crypto.public_key(secret)), key.public_key)
        self.assertNotIn(self.identity.did, key.secret_path)   # путь — не секрет, но и не адрес

    def test_first_event_is_announcement_and_chain_verifies(self):
        chain = self._chain()
        self.assertEqual(chain[0]['seq'], 0)
        self.assertEqual(chain[0]['type'], 'node.announced')
        self.assertEqual(chain[0]['subject'], self.identity.did)
        self.assertIn('jurisdiction', chain[0]['body'])
        self.assertEqual(fed_log.check_chain(chain, self.identity.keyring(), utc_now()), fed_log.OK)

    def test_seal_links_events(self):
        head = self.identity.head_seq
        self.Event._enqueue('catalog.offer.published', self.identity.did + '/offer/1',
                            {'title': 'Мука в/с', 'price': {'amount': '45.00', 'currency': 'RUB'}})
        self.Event._enqueue('catalog.offer.withdrawn', self.identity.did + '/offer/1',
                            {'reason': 'продано'})
        self.assertEqual(self.Event._seal(), 2)
        self.assertEqual(self.identity.head_seq, head + 2)
        chain = self._chain()
        self.assertEqual(chain[-1]['prev'], chain[-2]['id'])
        self.assertEqual(fed_log.check_chain(chain, self.identity.keyring(), utc_now()), fed_log.OK)
        self.assertTrue(fed_log.check_head(self.identity.head(), self.identity.keyring()))

    def test_float_rejected_in_authors_transaction(self):
        with self.assertRaises(TypeError):
            self.Event._enqueue('catalog.offer.published', self.identity.did + '/offer/2',
                                {'price': 45.5})

    def test_sealed_event_cannot_be_changed_or_deleted(self):
        event = self.Event.search([('node', '=', self.identity.did), ('seq', '=', 0)])
        with mute_logger('odoo.sql_db'), self.assertRaises(psycopg2.Error), self.cr.savepoint():
            self.cr.execute("UPDATE coop_fed_event SET body_json = '{}' WHERE id = %s", [event.id])
        with mute_logger('odoo.sql_db'), self.assertRaises(psycopg2.Error), self.cr.savepoint():
            self.cr.execute('DELETE FROM coop_fed_event WHERE id = %s', [event.id])

    def test_no_key_file_no_signature(self):
        """Копия базы без файла ключа не подписывает — и ничего не теряет."""
        key = self.identity._working_key()
        key.sudo().write({'secret_path': key.secret_path + '.missing'})
        pending = self.Event._enqueue('catalog.offer.published', self.identity.did + '/offer/3', {})
        with mute_logger('odoo.addons.coop_federation.models.fed_event'):
            self.assertEqual(self.Event._seal(), 0)
        self.assertEqual(pending.status, 'pending')
        self.assertTrue(self.identity.last_error)

    def test_detached_node_does_not_sign(self):
        self.identity.sudo().write({'state': 'detached'})
        with self.assertRaises(UserError):
            self.identity._secret()

    def test_addressed_body_only_for_addressee(self):
        self.Event._enqueue('deal.proposed', self.identity.did + '/deal/0b5c6f5e',
                            {'total': {'amount': '150000.00', 'currency': 'RUB'}}, to=[PEER])
        self.Event._seal()
        seq = self.identity.head_seq
        outsider = self.Event.journal(self.identity, since=seq, reader=None)[0]
        addressee = self.Event.journal(self.identity, since=seq, reader=PEER)[0]
        self.assertNotIn('body', outsider)
        self.assertIn('body', addressee)
        chain = self.Event.journal(self.identity, since=0, limit=1000, reader=None)
        self.assertEqual(fed_log.check_chain(chain, self.identity.keyring(), utc_now()), fed_log.OK)

    def test_did_document_verifies_journal(self):
        doc = json.loads(json.dumps(self.identity.did_document()))
        ring = fed_did.keyring(doc, self.identity.did)
        self.assertEqual(fed_log.check_chain(self._chain(), ring, utc_now()), fed_log.OK)


@tagged('post_install', '-at_install')
class TestFederationHttp(HttpCase):

    def setUp(self):
        super().setUp()
        self.identity = self.env['coop.fed.identity']._ensure()
        self.env['coop.fed.event']._enqueue('deal.proposed', self.identity.did + '/deal/http-1',
                                            {'total': {'amount': '10.00', 'currency': 'RUB'}},
                                            to=[PEER])
        self.env['coop.fed.event']._seal()
        # Сосед, чей DID-документ уже скачан (шаг 2 будет делать это сам).
        self.env['coop.fed.key'].create({
            'kid': PEER + '#key-1', 'owner_did': PEER,
            'public_key': fed_log.b64(crypto.public_key(PEER_SECRET)), 'purpose': 'working'})

    def test_did_json(self):
        response = self.url_open('/.well-known/did.json')
        self.assertEqual(response.status_code, 200)
        doc = response.json()
        self.assertEqual(doc['id'], self.identity.did)
        self.assertTrue(doc['verificationMethod'][0]['publicKeyMultibase'].startswith('z6Mk'))
        self.assertNotIn('Set-Cookie', response.headers)

    def _last(self, headers=None, **query):
        query.setdefault('since', str(self.identity.head_seq))
        url = '/federation/log?' + '&'.join('%s=%s' % kv for kv in query.items())
        response = self.url_open(url, headers=headers or {})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_log_outsider_gets_envelope_only(self):
        payload = self._last(**{'for': PEER})
        self.assertNotIn('body', payload['events'][0])
        self.assertIn('body_hash', payload['events'][0])
        self.assertEqual(payload['head']['seq'], self.identity.head_seq)

    def test_log_signed_addressee_gets_body(self):
        query = {'since': str(self.identity.head_seq), 'for': PEER}
        headers = fed_reader.sign(PEER, PEER + '#key-1', PEER_SECRET, 'GET', '/federation/log',
                                  query, utc_now())
        payload = self._last(headers=headers, **query)
        self.assertEqual(payload['events'][0]['body']['total']['amount'], '10.00')

    def test_log_whole_chain_verifies_with_published_keys(self):
        doc = self.url_open('/.well-known/did.json').json()
        events = self._last(since='0', limit='1000')['events']
        ring = fed_did.keyring(doc, self.identity.did)
        self.assertEqual(fed_log.check_chain(events, ring, utc_now()), fed_log.OK)
